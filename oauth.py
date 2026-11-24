"""OAuth 2.1 authorization server for hop's MCP endpoint (so claude.ai custom connectors work).

Built on the pinned `mcp` SDK (1.30): its handlers do the protocol work (dynamic client
registration, /authorize parameter and PKCE validation, /token, /revoke) and this module
supplies the storage (`HopOAuthProvider`, Postgres) plus hop's own pages: sign-in and consent.

Mounted at /oauth, so hop's own POST /register and POST /token are untouched:
  /oauth/authorize  /oauth/token  /oauth/register  /oauth/revoke  /oauth/consent
Discovery documents are served at /.well-known/... by main.py using the helpers here.

Tokens, refresh tokens and authorization codes are stored only as SHA-256 hashes.
Not supported by SDK 1.30: Client ID Metadata Documents (clients must use dynamic registration).
"""
import base64
import contextlib
import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Mapping, Optional
from urllib.parse import urlparse

from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.middleware.client_auth import AuthenticationError, ClientAuthenticator
from mcp.server.auth.routes import cors_middleware, create_auth_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl

from database import db_pool, redis_client
from pages import render_page
from security import SECRET_KEY, verify_password

logger = logging.getLogger(__name__)

SCOPE = "mcp"
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 86400
CODE_TTL = 60
PENDING_TTL = 600
SESSION_TTL = 600
CSRF_TTL = 900
SESSION_COOKIE = "hop_oauth"
ISSUER_PATH = "/oauth"
MCP_PATH = "/mcp"
MAX_REDIRECT_URIS = 10


# ---- Pure helpers (no database) -------------------------------------------------

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """RFC 7636 S256: BASE64URL(SHA256(verifier)) == challenge. Rejects malformed verifiers."""
    if not (43 <= len(code_verifier) <= 128) or not all(c.isalnum() or c in "-._~" for c in code_verifier):
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return hmac.compare_digest(expected, code_challenge)


def redirect_uri_allowed(uri: str) -> bool:
    """https only, or http on a loopback host (any port) for native clients. No fragments."""
    try:
        p = urlparse(uri)
        host = p.hostname
    except ValueError:
        return False
    if not host or p.fragment or p.username or p.password:
        return False
    if p.scheme == "https":
        return True
    return p.scheme == "http" and host in ("localhost", "127.0.0.1", "::1")


def is_expired(expires_at: float, now: Optional[float] = None) -> bool:
    return expires_at <= (time.time() if now is None else now)


def public_origin(headers: Mapping[str, str], scheme: str = "http") -> str:
    """Public origin of this server: PUBLIC_BASE_URL if set, else from the request headers."""
    env = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if env:
        return env
    h = {k.lower(): v for k, v in headers.items()}
    proto = h.get("x-forwarded-proto", scheme).split(",")[0].strip() or scheme
    return f"{proto}://{h.get('host', 'localhost')}"


def resource_url(origin: str) -> str:
    return origin + MCP_PATH


def issuer_url(origin: str) -> str:
    return origin + ISSUER_PATH


def resource_matches(resource: Optional[str], origin: str) -> bool:
    """RFC 8707: a `resource` parameter, when given, must identify the /mcp endpoint."""
    if resource is None:
        return True
    return resource.rstrip("/") == resource_url(origin)


def resource_metadata_url(origin: str) -> str:
    return f"{origin}/.well-known/oauth-protected-resource{MCP_PATH}"


def authorization_server_metadata(origin: str) -> dict:
    iss = issuer_url(origin)
    return {
        "issuer": iss,
        "authorization_endpoint": f"{iss}/authorize",
        "token_endpoint": f"{iss}/token",
        "registration_endpoint": f"{iss}/register",
        "revocation_endpoint": f"{iss}/revoke",
        "scopes_supported": [SCOPE],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "revocation_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
        "client_id_metadata_document_supported": False,
    }


def protected_resource_metadata(origin: str) -> dict:
    return {
        "resource": resource_url(origin),
        "authorization_servers": [issuer_url(origin)],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "hop",
    }


def _sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def make_csrf(req_id: str, uid: int, now: Optional[float] = None, secret: str = SECRET_KEY) -> str:
    """CSRF token bound to one authorization request and user (0 before sign-in), signed with SECRET_KEY."""
    exp = int((time.time() if now is None else now) + CSRF_TTL)
    return f"{exp}.{_sign(secret, f'csrf|{req_id}|{uid}|{exp}')}"


def check_csrf(token: str, req_id: str, uid: int, now: Optional[float] = None, secret: str = SECRET_KEY) -> bool:
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < (time.time() if now is None else now):
        return False
    return hmac.compare_digest(sig, _sign(secret, f"csrf|{req_id}|{uid}|{exp}"))


def make_session(uid: int, now: Optional[float] = None, secret: str = SECRET_KEY) -> str:
    exp = int((time.time() if now is None else now) + SESSION_TTL)
    payload = f"{uid}:{exp}"
    return f"{payload}.{_sign(secret, 'session|' + payload)}"


def read_session(value: Optional[str], now: Optional[float] = None, secret: str = SECRET_KEY) -> Optional[int]:
    if not value:
        return None
    try:
        payload, sig = value.rsplit(".", 1)
        uid_s, exp_s = payload.split(":")
        uid, exp = int(uid_s), int(exp_s)
    except ValueError:
        return None
    if exp < (time.time() if now is None else now):
        return None
    if not hmac.compare_digest(sig, _sign(secret, "session|" + payload)):
        return None
    return uid


# ---- Rate limiting ----------------------------------------------------------------

def over_limit(prefix: str, ident: str, limit: int, window_seconds: int) -> bool:
    """Fixed-window counter in Redis. Fails open if Redis is unavailable."""
    window = int(time.time() // window_seconds)
    key = f"{prefix}:{ident}:{window}"
    try:
        n = redis_client.incr(key)
        if n == 1:
            redis_client.expire(key, window_seconds * 2)
        return n > limit
    except Exception as e:  # pragma: no cover
        logger.error("OAuth rate limit check failed: %s", type(e).__name__)
        return False


def client_ip(headers: Mapping[str, str], fallback: str = "unknown") -> str:
    h = {k.lower(): v for k, v in headers.items()}
    fwd = h.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else fallback


class RateLimited:
    """ASGI wrapper that rejects POSTs over a per-IP limit with a JSON 429."""

    def __init__(self, app: ASGIApp, name: str, limit: int, window_seconds: int):
        self.app, self.name, self.limit, self.window = app, name, limit, window_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST":
            headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
            ip = client_ip(headers, (scope.get("client") or ("unknown",))[0])
            if await run_in_threadpool(over_limit, self.name, ip, self.limit, self.window):
                resp = JSONResponse(
                    {"error": "temporarily_unavailable", "error_description": "Too many requests. Wait a minute and try again."},
                    status_code=429,
                    headers={"Retry-After": "60", "Cache-Control": "no-store"},
                )
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


# ---- Storage (sync psycopg2; the provider calls these through a thread pool) -----------

@contextlib.contextmanager
def db_conn() -> Iterator:
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        with contextlib.suppress(Exception):
            conn.rollback()
        db_pool.putconn(conn)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def save_client(info: OAuthClientInformationFull) -> None:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO oauth_clients (client_id, client_info) VALUES (%s, %s)",
            (info.client_id, info.model_dump_json()),
        )
        conn.commit()


def load_client(client_id: str) -> Optional[OAuthClientInformationFull]:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT client_info FROM oauth_clients WHERE client_id = %s", (client_id,))
        row = cur.fetchone()
    return OAuthClientInformationFull.model_validate_json(row[0]) if row else None


def save_pending(data: dict) -> str:
    req_id = secrets.token_urlsafe(24)
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM oauth_pending WHERE expires_at < now()")
        cur.execute(
            "INSERT INTO oauth_pending (id, data, expires_at) VALUES (%s, %s, %s)",
            (req_id, json.dumps(data), _now() + timedelta(seconds=PENDING_TTL)),
        )
        conn.commit()
    return req_id


def get_pending(req_id: str) -> Optional[dict]:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT data FROM oauth_pending WHERE id = %s AND expires_at > now()", (req_id,))
        row = cur.fetchone()
    return json.loads(row[0]) if row else None


def take_pending(req_id: str) -> Optional[dict]:
    """Fetch and delete in one statement, so one authorization request is decided once."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM oauth_pending WHERE id = %s AND expires_at > now() RETURNING data", (req_id,))
        row = cur.fetchone()
        conn.commit()
    return json.loads(row[0]) if row else None


def create_code(user_id: int, pending: dict) -> str:
    code = new_token("hopc_")
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM oauth_codes WHERE expires_at < now()")
        cur.execute(
            "INSERT INTO oauth_codes (code_hash, user_id, data, expires_at) VALUES (%s, %s, %s, %s)",
            (hash_token(code), user_id, json.dumps(pending), _now() + timedelta(seconds=CODE_TTL)),
        )
        conn.commit()
    return code


def consume_code(code: str) -> Optional[dict]:
    """Single use: the row is deleted whether or not the exchange then succeeds."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM oauth_codes WHERE code_hash = %s RETURNING user_id, data, expires_at",
            (hash_token(code),),
        )
        row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return {"user_id": row[0], "data": json.loads(row[1]), "expires_at": row[2].timestamp()}


def issue_tokens(user_id: int, client_id: str, scope: str, resource: Optional[str],
                 family_id: Optional[str] = None, rotate_refresh_hash: Optional[str] = None) -> OAuthToken:
    """Create a new access/refresh pair. When rotating, the old pair is revoked atomically first."""
    access, refresh = new_token("hopat_"), new_token("hoprt_")
    now = _now()
    with db_conn() as conn:
        cur = conn.cursor()
        if rotate_refresh_hash is not None:
            cur.execute(
                "UPDATE oauth_tokens SET revoked_at = now() WHERE refresh_hash = %s AND revoked_at IS NULL",
                (rotate_refresh_hash,),
            )
            if cur.rowcount != 1:  # someone else already used this refresh token
                conn.rollback()
                raise TokenError("invalid_grant", "refresh token is no longer valid")
        cur.execute(
            "INSERT INTO oauth_tokens (family_id, access_hash, refresh_hash, user_id, client_id, scope, resource, "
            "access_expires_at, refresh_expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (family_id or secrets.token_hex(16), hash_token(access), hash_token(refresh), user_id, client_id,
             scope, resource, now + timedelta(seconds=ACCESS_TTL), now + timedelta(seconds=REFRESH_TTL)),
        )
        conn.commit()
    return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_TTL, scope=scope, refresh_token=refresh)


def lookup_access_token(token: str, touch: bool = True) -> Optional[dict]:
    """Valid (unrevoked, unexpired) access token -> row info, else None."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, client_id, scope, resource, access_expires_at FROM oauth_tokens "
            "WHERE access_hash = %s AND revoked_at IS NULL AND access_expires_at > now()",
            (hash_token(token),),
        )
        row = cur.fetchone()
        if row and touch:
            cur.execute("UPDATE oauth_tokens SET last_used_at = now() WHERE id = %s", (row[0],))
            conn.commit()
    if not row:
        return None
    return {"id": row[0], "user_id": row[1], "client_id": row[2], "scope": row[3], "resource": row[4],
            "expires_at": int(row[5].timestamp())}


def lookup_refresh_token(token: str) -> Optional[dict]:
    """Valid refresh token -> row info. Presenting an already-revoked one revokes its whole family."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, client_id, scope, resource, refresh_expires_at, revoked_at, family_id, "
            "refresh_expires_at > now() FROM oauth_tokens WHERE refresh_hash = %s",
            (hash_token(token),),
        )
        row = cur.fetchone()
        if row and row[5] is not None:
            cur.execute("UPDATE oauth_tokens SET revoked_at = now() WHERE family_id = %s AND revoked_at IS NULL", (row[6],))
            conn.commit()
            return None
    if not row or not row[7]:
        return None
    return {"user_id": row[0], "client_id": row[1], "scope": row[2], "resource": row[3],
            "expires_at": int(row[4].timestamp()), "family_id": row[6]}


def revoke_by_token(token: str, client_id: Optional[str] = None) -> None:
    """Revoke the token's whole family (access and refresh). With client_id, only if it belongs to that client."""
    h = hash_token(token)
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE oauth_tokens SET revoked_at = now() WHERE revoked_at IS NULL AND family_id IN "
            "(SELECT family_id FROM oauth_tokens WHERE (access_hash = %s OR refresh_hash = %s) "
            "AND (%s IS NULL OR client_id = %s))",
            (h, h, client_id, client_id),
        )
        conn.commit()


def list_grants(user_id: int) -> list[dict]:
    """Apps this user has connected (active refresh tokens), one entry per client."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT t.client_id, c.client_info, MIN(t.created_at), MAX(t.last_used_at) FROM oauth_tokens t "
            "LEFT JOIN oauth_clients c ON c.client_id = t.client_id "
            "WHERE t.user_id = %s AND t.revoked_at IS NULL AND t.refresh_expires_at > now() "
            "GROUP BY t.client_id, c.client_info ORDER BY MIN(t.created_at) DESC",
            (user_id,),
        )
        rows = cur.fetchall()
    out = []
    for client_id, info, created, used in rows:
        name = None
        if info:
            with contextlib.suppress(Exception):
                name = json.loads(info).get("client_name")
        out.append({
            "client_id": client_id,
            "client_name": name or "Unnamed app",
            "created_at": created.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if created else None,
            "last_used_at": used.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if used else None,
        })
    return out


def revoke_grant(user_id: int, client_id: str) -> bool:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM oauth_tokens WHERE user_id = %s AND client_id = %s", (user_id, client_id))
        deleted = cur.rowcount
        conn.commit()
    return deleted > 0


def check_credentials(username: str, password: str) -> Optional[int]:
    """Same check as POST /token."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, password FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
    if row is None or not verify_password(password, row[1]):
        return None
    return row[0]


def username_of(user_id: int) -> Optional[str]:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    return row[0] if row else None


# ---- SDK provider --------------------------------------------------------------------

class HopOAuthProvider:
    """OAuthAuthorizationServerProvider backed by Postgres."""

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        return await run_in_threadpool(load_client, client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in (client_info.redirect_uris or [])]
        if not uris or len(uris) > MAX_REDIRECT_URIS:
            raise RegistrationError("invalid_redirect_uri", f"Provide 1 to {MAX_REDIRECT_URIS} redirect_uris.")
        for u in uris:
            if not redirect_uri_allowed(u):
                raise RegistrationError(
                    "invalid_redirect_uri",
                    "redirect_uris must use https, or http on localhost or 127.0.0.1, with no fragment.",
                )
        if client_info.client_name:
            client_info.client_name = client_info.client_name.strip()[:100] or None
        client_info.scope = SCOPE
        await run_in_threadpool(save_client, client_info)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Called by the SDK once client, redirect_uri and PKCE parameters are validated.
        Store the request and send the browser to hop's sign-in/consent page."""
        req_id = await run_in_threadpool(save_pending, {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "redirect_explicit": params.redirect_uri_provided_explicitly,
            "state": params.state,
            "code_challenge": params.code_challenge,
            "resource": params.resource,
        })
        return f"{ISSUER_PATH}/consent?req={req_id}"

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> Optional[AuthorizationCode]:
        row = await run_in_threadpool(consume_code, authorization_code)  # consumed even if the exchange fails
        if row is None:
            return None
        d = row["data"]
        if d["client_id"] != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=[SCOPE],
            expires_at=row["expires_at"],
            client_id=d["client_id"],
            code_challenge=d["code_challenge"],
            redirect_uri=AnyUrl(d["redirect_uri"]),
            redirect_uri_provided_explicitly=d["redirect_explicit"],
            resource=d.get("resource"),
            subject=str(row["user_id"]),
        )

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode) -> OAuthToken:
        return await run_in_threadpool(
            issue_tokens, int(authorization_code.subject or 0), client.client_id or "", SCOPE, authorization_code.resource,
        )

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> Optional[RefreshToken]:
        row = await run_in_threadpool(lookup_refresh_token, refresh_token)
        if row is None or row["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=row["client_id"], scopes=[row["scope"]],
                            expires_at=row["expires_at"], resource=row["resource"], subject=str(row["user_id"]))

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        row = await run_in_threadpool(lookup_refresh_token, refresh_token.token)
        if row is None:
            raise TokenError("invalid_grant", "refresh token is no longer valid")
        return await run_in_threadpool(
            issue_tokens, row["user_id"], row["client_id"], row["scope"], row["resource"],
            row["family_id"], hash_token(refresh_token.token),
        )

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        row = await run_in_threadpool(lookup_access_token, token, False)
        if row is None:
            return None
        return AccessToken(token=token, client_id=row["client_id"], scopes=[row["scope"]],
                           expires_at=row["expires_at"], resource=row["resource"], subject=str(row["user_id"]))

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await run_in_threadpool(revoke_by_token, token.token)


provider = HopOAuthProvider()


# ---- Sign-in and consent pages ---------------------------------------------------------

def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _error_page(message: str, status: int = 400) -> Response:
    return render_page("Cannot continue", f"<h1>Cannot continue</h1><p>{_e(message)}</p>", status)


def _login_page(req_id: str, client_name: str, error: str = "", status: int = 200) -> Response:
    body = f"""<h1>Sign in to hop</h1>
<p><strong>{_e(client_name)}</strong> is asking to connect to your hop account.</p>
<form class="card" method="post" action="{ISSUER_PATH}/consent/login" autocomplete="on">
<input type="hidden" name="req" value="{_e(req_id)}">
<input type="hidden" name="csrf" value="{_e(make_csrf(req_id, 0))}">
<label for="u">Username</label>
<input id="u" name="username" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" required>
<label for="p">Password</label>
<input id="p" name="password" type="password" autocomplete="current-password" required>
<p class="err" role="alert">{_e(error)}</p>
<button class="primary" type="submit" style="width:100%">Sign in</button>
</form>"""
    return render_page("Sign in", body, status)


def _consent_page(req_id: str, uid: int, username: str, client_name: str, redirect_host: str) -> Response:
    body = f"""<h1>Connect {_e(client_name)} to hop?</h1>
<p>Signed in as <strong>{_e(username)}</strong>.</p>
<form class="card" method="post" action="{ISSUER_PATH}/consent">
<input type="hidden" name="req" value="{_e(req_id)}">
<input type="hidden" name="csrf" value="{_e(make_csrf(req_id, uid))}">
<p><strong>{_e(client_name)}</strong> wants to:</p>
<ul class="perms">
<li>read your links and click analytics</li>
<li>create and edit links</li>
</ul>
<p class="small">After you allow, you will be sent back to <span class="mono">{_e(redirect_host)}</span>.
The name above is chosen by the app, not verified by hop. You can revoke access at any time from
Connect to Claude in hop.</p>
<div class="row">
<button type="submit" name="decision" value="deny">Deny</button>
<button class="primary" type="submit" name="decision" value="allow">Allow</button>
</div>
</form>"""
    return render_page("Authorize", body, 200)


def _client_name(info: Optional[OAuthClientInformationFull]) -> str:
    return (info.client_name if info and info.client_name else "An application")


async def consent_get(request: Request) -> Response:
    req_id = request.query_params.get("req", "")
    pending = await run_in_threadpool(get_pending, req_id)
    if not pending:
        return _error_page("This authorization request has expired. Start again from the app.")
    client = await run_in_threadpool(load_client, pending["client_id"])
    uid = read_session(request.cookies.get(SESSION_COOKIE))
    username = await run_in_threadpool(username_of, uid) if uid else None
    if uid is None or username is None:
        return _login_page(req_id, _client_name(client))
    return _consent_page(req_id, uid, username, _client_name(client), urlparse(pending["redirect_uri"]).netloc)


async def login_post(request: Request) -> Response:
    form = await request.form()
    req_id = str(form.get("req", ""))
    if not check_csrf(str(form.get("csrf", "")), req_id, 0):
        return _error_page("This form expired. Reload the page and try again.", 403)
    pending = await run_in_threadpool(get_pending, req_id)
    if not pending:
        return _error_page("This authorization request has expired. Start again from the app.")
    client = await run_in_threadpool(load_client, pending["client_id"])
    ip = client_ip(request.headers, request.client.host if request.client else "unknown")
    if await run_in_threadpool(over_limit, "oauth-login", ip, 10, 60):  # same 10/min as POST /token
        return _login_page(req_id, _client_name(client), "Too many attempts. Wait a minute and try again.", 429)
    uid = await run_in_threadpool(check_credentials, str(form.get("username", "")), str(form.get("password", "")))
    if uid is None:
        logger.warning("Failed OAuth sign-in attempt")
        return _login_page(req_id, _client_name(client), "Incorrect username or password.", 401)
    resp = RedirectResponse(f"{ISSUER_PATH}/consent?req={req_id}", status_code=303, headers={"Cache-Control": "no-store"})
    origin = public_origin(request.headers, request.url.scheme)
    resp.set_cookie(SESSION_COOKIE, make_session(uid), max_age=SESSION_TTL, path=ISSUER_PATH,
                    httponly=True, samesite="lax", secure=origin.startswith("https"))
    return resp


async def consent_post(request: Request) -> Response:
    form = await request.form()
    req_id = str(form.get("req", ""))
    uid = read_session(request.cookies.get(SESSION_COOKIE))
    if uid is None:
        return RedirectResponse(f"{ISSUER_PATH}/consent?req={req_id}", status_code=303)
    if not check_csrf(str(form.get("csrf", "")), req_id, uid):
        return _error_page("This form expired. Reload the page and try again.", 403)
    pending = await run_in_threadpool(take_pending, req_id)
    if not pending:
        return _error_page("This authorization request has expired or was already used. Start again from the app.")
    redirect_uri = pending["redirect_uri"]  # validated against the client's registered URIs by the SDK
    headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    if form.get("decision") != "allow":
        url = construct_redirect_uri(redirect_uri, error="access_denied", state=pending.get("state"))
        return RedirectResponse(url, status_code=303, headers=headers)
    code = await run_in_threadpool(create_code, uid, pending)
    url = construct_redirect_uri(redirect_uri, code=code, state=pending.get("state"))
    return RedirectResponse(url, status_code=303, headers=headers)


# ---- App -----------------------------------------------------------------------------

def _authorize_endpoint(sdk_handler: AuthorizationHandler):
    async def endpoint(request: Request) -> Response:
        resource = request.query_params.get("resource") if request.method == "GET" else None
        origin = public_origin(request.headers, request.url.scheme)
        if resource is not None and not resource_matches(resource, origin):
            return JSONResponse(
                {"error": "invalid_target", "error_description": f"resource must be {resource_url(origin)}"},
                status_code=400, headers={"Cache-Control": "no-store"},
            )
        return await sdk_handler.handle(request)

    return endpoint


def _revoke_endpoint():
    """RFC 7009 revocation. The SDK's handler requires a `client_secret` field even for public
    clients (its model has no default), so hop handles this endpoint itself."""
    authenticator = ClientAuthenticator(provider)

    async def endpoint(request: Request) -> Response:
        headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
        try:
            client = await authenticator.authenticate_request(request)
        except AuthenticationError as e:
            return JSONResponse({"error": "unauthorized_client", "error_description": e.message}, status_code=401, headers=headers)
        form = await request.form()
        token = form.get("token")
        if not isinstance(token, str) or not token:
            return JSONResponse({"error": "invalid_request", "error_description": "token is required"}, status_code=400, headers=headers)
        # Unknown tokens and other clients' tokens are ignored; the answer is 200 either way (RFC 7009).
        await run_in_threadpool(revoke_by_token, token, client.client_id)
        return Response(status_code=200, headers=headers)

    return cors_middleware(endpoint, ["POST", "OPTIONS"])


def build_app() -> Starlette:
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") or "http://localhost"
    sdk_routes = create_auth_routes(
        provider,
        issuer_url=AnyHttpUrl(issuer_url(base)),
        client_registration_options=ClientRegistrationOptions(enabled=True, default_scopes=[SCOPE]),
        revocation_options=RevocationOptions(enabled=True),
    )
    routes = []
    for r in sdk_routes:
        if r.path == "/.well-known/oauth-authorization-server":
            continue  # served at the server root by main.py, with the right issuer
        if r.path == "/authorize":
            routes.append(Route("/authorize", endpoint=_authorize_endpoint(AuthorizationHandler(provider)), methods=["GET", "POST"]))
        elif r.path == "/register":
            routes.append(Route(r.path, endpoint=RateLimited(r.app, "oauth-register", 20, 3600), methods=list(r.methods or [])))
        elif r.path == "/revoke":
            routes.append(Route("/revoke", endpoint=_revoke_endpoint(), methods=["POST", "OPTIONS"]))
        elif r.path == "/token":
            routes.append(Route(r.path, endpoint=RateLimited(r.app, "oauth-token", 60, 60), methods=list(r.methods or [])))
        else:
            routes.append(r)
    routes += [
        Route("/consent", consent_get, methods=["GET"]),
        Route("/consent", consent_post, methods=["POST"]),
        Route("/consent/login", login_post, methods=["POST"]),
    ]
    return Starlette(routes=routes)


oauth_app = build_app()
