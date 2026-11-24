"""OAuth flow through the real SDK handlers and hop's pages, with Postgres replaced by an in-memory store.

This checks the wiring (routes, validation, CSRF, PKCE, redirect rules, token and refresh handling).
The SQL itself is covered by tests/e2e_oauth.py against a running server.
"""
import base64
import hashlib
import re
import secrets
import time
from urllib.parse import parse_qs, urlparse

import pytest
from mcp.server.auth.provider import TokenError

import oauth

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
REDIRECT = "http://localhost:3118/callback"


class FakeStore:
    """Same semantics as the SQL functions in oauth.py."""

    def __init__(self):
        self.clients, self.pending, self.codes, self.tokens = {}, {}, {}, []

    def save_client(self, info):
        self.clients[info.client_id] = info

    def load_client(self, cid):
        return self.clients.get(cid)

    def save_pending(self, data):
        rid = secrets.token_urlsafe(12)
        self.pending[rid] = data
        return rid

    def get_pending(self, rid):
        return self.pending.get(rid)

    def take_pending(self, rid):
        return self.pending.pop(rid, None)

    def create_code(self, uid, pending):
        code = oauth.new_token("hopc_")
        self.codes[oauth.hash_token(code)] = {"user_id": uid, "data": pending, "expires_at": time.time() + oauth.CODE_TTL}
        return code

    def consume_code(self, code):
        return self.codes.pop(oauth.hash_token(code), None)

    def issue_tokens(self, uid, cid, scope, resource, family=None, rotate=None):
        if rotate is not None:
            row = next((t for t in self.tokens if t["rh"] == rotate and not t["revoked"]), None)
            if row is None:
                raise TokenError("invalid_grant", "refresh token is no longer valid")
            row["revoked"] = True
        access, refresh = oauth.new_token("hopat_"), oauth.new_token("hoprt_")
        self.tokens.append({"id": len(self.tokens) + 1, "ah": oauth.hash_token(access), "rh": oauth.hash_token(refresh),
                            "user_id": uid, "client_id": cid, "scope": scope, "resource": resource,
                            "family": family or secrets.token_hex(4), "revoked": False})
        return oauth.OAuthToken(access_token=access, expires_in=3600, scope=scope, refresh_token=refresh)

    def lookup_access(self, token, touch=True):
        h = oauth.hash_token(token)
        r = next((t for t in self.tokens if t["ah"] == h and not t["revoked"]), None)
        return r and {**r, "expires_at": int(time.time()) + 3600}

    def lookup_refresh(self, token):
        h = oauth.hash_token(token)
        r = next((t for t in self.tokens if t["rh"] == h), None)
        if r and r["revoked"]:  # reuse of a rotated token: kill the family
            for t in self.tokens:
                if t["family"] == r["family"]:
                    t["revoked"] = True
            return None
        return r and {**r, "expires_at": int(time.time()) + 86400, "family_id": r["family"]}

    def revoke(self, token, client_id=None):
        h = oauth.hash_token(token)
        fam = {t["family"] for t in self.tokens if h in (t["ah"], t["rh"]) and client_id in (None, t["client_id"])}
        for t in self.tokens:
            if t["family"] in fam:
                t["revoked"] = True


@pytest.fixture()
def store(monkeypatch):
    s = FakeStore()
    for name, fn in {
        "save_client": s.save_client, "load_client": s.load_client, "save_pending": s.save_pending,
        "get_pending": s.get_pending, "take_pending": s.take_pending, "create_code": s.create_code,
        "consume_code": s.consume_code, "issue_tokens": s.issue_tokens, "lookup_access_token": s.lookup_access,
        "lookup_refresh_token": s.lookup_refresh, "revoke_by_token": s.revoke,
        "check_credentials": lambda u, p: 7 if (u, p) == ("alice", "correct horse") else None,
        "username_of": lambda uid: "alice" if uid == 7 else None,
        "over_limit": lambda *a, **k: False,
    }.items():
        monkeypatch.setattr(oauth, name, fn)
    return s


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def register(client, **over):
    body = {"redirect_uris": [REDIRECT], "client_name": "Test <b>App</b>", "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"], **over}
    return client.post("/oauth/register", json=body)


def authorize(client, cid, challenge, **over):
    q = {"client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "code_challenge": challenge,
         "code_challenge_method": "S256", "state": "st-123", "resource": "https://hop.test/mcp", **over}
    return client.get("/oauth/authorize", params={k: v for k, v in q.items() if v is not None})


def csrf_from(html_text):
    return re.search(r'name="csrf" value="([^"]+)"', html_text).group(1)


def full_login_and_consent(client, loc, decision="allow"):
    req = parse_qs(urlparse(loc).query)["req"][0]
    page = client.get(loc)
    assert page.status_code == 200
    if "Sign in to hop" in page.text:  # a repeat visit within the session cookie lifetime goes straight to consent
        r = client.post("/oauth/consent/login", data={"req": req, "csrf": csrf_from(page.text), "username": "alice", "password": "correct horse"})
        assert r.status_code == 303
        page = client.get(loc)
    assert "wants to" in page.text and "read your links and click analytics" in page.text
    return req, client.post("/oauth/consent", data={"req": req, "csrf": csrf_from(page.text), "decision": decision})


def get_tokens(client, cid):
    verifier, challenge = pkce()
    r = authorize(client, cid, challenge)
    assert r.status_code == 302 and r.headers["location"].startswith("/oauth/consent?req=")
    _, done = full_login_and_consent(client, r.headers["location"])
    assert done.status_code == 303
    q = parse_qs(urlparse(done.headers["location"]).query)
    assert q["state"] == ["st-123"]
    return verifier, q["code"][0]


def exchange(client, cid, code, verifier, redirect=REDIRECT):
    return client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": cid,
                                               "redirect_uri": redirect, "code_verifier": verifier})


def test_discovery_and_401_challenge(client, store):
    r = client.post("/mcp", json={}, headers=HEADERS)
    assert r.status_code == 401
    assert 'resource_metadata="https://hop.test/.well-known/oauth-protected-resource/mcp"' in r.headers["www-authenticate"]
    assert r.json()["success"] is False
    for path in ("/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-protected-resource"):
        j = client.get(path).json()
        assert j["resource"] == "https://hop.test/mcp" and j["authorization_servers"] == ["https://hop.test/oauth"]
    for path in ("/.well-known/oauth-authorization-server", "/.well-known/oauth-authorization-server/oauth"):
        j = client.get(path).json()
        assert j["issuer"] == "https://hop.test/oauth" and j["registration_endpoint"].endswith("/oauth/register")


def test_existing_register_and_token_routes_are_untouched(client, store):
    # hop's own sign-up and login still answer at the old paths (validation errors, not 404/405).
    assert client.post("/register", json={}).status_code == 422
    assert client.post("/token", data={}).status_code == 422


def test_registration_validates_redirect_uris(client, store):
    assert register(client).status_code == 201
    for bad in ("http://evil.example/cb", "javascript:alert(1)", "myapp://cb", "https://x.example/cb#f"):
        r = register(client, redirect_uris=[bad])
        assert r.status_code == 400 and r.json()["error"] == "invalid_redirect_uri", bad
    assert register(client, redirect_uris=["https://claude.ai/api/mcp/auth_callback"]).status_code == 201


def test_authorize_rejections(client, store):
    cid = register(client).json()["client_id"]
    _, challenge = pkce()
    # unregistered redirect_uri: shown as an error, never redirected to
    r = authorize(client, cid, challenge, redirect_uri="https://evil.example/cb")
    assert r.status_code == 400 and "location" not in r.headers
    # unknown client
    assert authorize(client, "nope", challenge).status_code == 400
    # PKCE: plain and missing challenge are rejected
    assert authorize(client, cid, challenge, code_challenge_method="plain").status_code in (302, 400)
    r = authorize(client, cid, challenge, code_challenge_method="plain")
    assert "consent" not in r.headers.get("location", "")
    r = authorize(client, cid, None)
    assert "consent" not in r.headers.get("location", "")
    # wrong resource
    r = authorize(client, cid, challenge, resource="https://hop.test/other")
    assert r.status_code == 400 and r.json()["error"] == "invalid_target"
    assert not store.pending


def test_full_flow_login_consent_code_token_mcp_refresh_revoke(client, store):
    cid = register(client).json()["client_id"]
    verifier, code = get_tokens(client, cid)
    r = exchange(client, cid, code, verifier)
    assert r.status_code == 200, r.text
    tok = r.json()
    assert tok["token_type"] == "Bearer" and tok["expires_in"] == 3600 and tok["scope"] == "mcp"
    assert tok["access_token"].startswith("hopat_") and tok["refresh_token"].startswith("hoprt_")

    # the access token opens /mcp
    h = {**HEADERS, "Authorization": f"Bearer {tok['access_token']}"}
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=h)
    assert r.status_code == 200 and "list_links" in r.text

    # refresh rotates; the old refresh token and old access token stop working
    r2 = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": cid})
    assert r2.status_code == 200, r2.text
    new = r2.json()
    assert new["refresh_token"] != tok["refresh_token"]
    r3 = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": cid})
    assert r3.status_code == 400 and r3.json()["error"] == "invalid_grant"
    assert client.post("/mcp", json={}, headers=h).status_code == 401
    # reusing a rotated refresh token also killed the new family
    h2 = {**HEADERS, "Authorization": f"Bearer {new['access_token']}"}
    assert client.post("/mcp", json={}, headers=h2).status_code == 401


def test_revocation(client, store):
    cid = register(client).json()["client_id"]
    verifier, code = get_tokens(client, cid)
    tok = exchange(client, cid, code, verifier).json()
    h = {**HEADERS, "Authorization": f"Bearer {tok['access_token']}"}
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=h).status_code == 200
    rv = client.post("/oauth/revoke", data={"token": tok["refresh_token"], "client_id": cid})
    assert rv.status_code == 200, rv.text
    assert client.post("/mcp", json={}, headers=h).status_code == 401


def test_wrong_verifier_reused_code_and_redirect_mismatch(client, store):
    cid = register(client).json()["client_id"]
    verifier, code = get_tokens(client, cid)
    bad = exchange(client, cid, code, secrets.token_urlsafe(48))
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_grant"
    # the failed attempt consumed the code, so even the right verifier fails now
    assert exchange(client, cid, code, verifier).status_code == 400

    verifier, code = get_tokens(client, cid)
    assert exchange(client, cid, code, verifier, redirect="http://localhost:9999/other").status_code == 400
    verifier, code = get_tokens(client, cid)
    assert exchange(client, cid, code, verifier).status_code == 200
    assert exchange(client, cid, code, verifier).status_code == 400  # reused


def test_code_belongs_to_one_client(client, store):
    a = register(client).json()["client_id"]
    b = register(client).json()["client_id"]
    verifier, code = get_tokens(client, a)
    assert exchange(client, b, code, verifier).status_code == 400


def test_login_errors_csrf_and_deny(client, store):
    client.cookies.clear()
    cid = register(client).json()["client_id"]
    _, challenge = pkce()
    loc = authorize(client, cid, challenge).headers["location"]
    req = parse_qs(urlparse(loc).query)["req"][0]
    page = client.get(loc)
    assert "Test &lt;b&gt;App&lt;/b&gt;" in page.text and "<b>App</b>" not in page.text  # client name escaped
    good = csrf_from(page.text)
    assert client.post("/oauth/consent/login", data={"req": req, "csrf": "bad", "username": "alice", "password": "correct horse"}).status_code == 403
    r = client.post("/oauth/consent/login", data={"req": req, "csrf": good, "username": "alice", "password": "wrong"})
    assert r.status_code == 401 and "Incorrect username or password" in r.text
    client.post("/oauth/consent/login", data={"req": req, "csrf": good, "username": "alice", "password": "correct horse"})
    # consent without a valid CSRF token is refused and consumes nothing
    r = client.post("/oauth/consent", data={"req": req, "csrf": good, "decision": "allow"})  # login token (uid 0), not the consent one
    assert r.status_code == 403 and req in store.pending
    consent_csrf = csrf_from(client.get(loc).text)
    deny = client.post("/oauth/consent", data={"req": req, "csrf": consent_csrf, "decision": "deny"})
    q = parse_qs(urlparse(deny.headers["location"]).query)
    assert deny.status_code == 303 and q["error"] == ["access_denied"] and q["state"] == ["st-123"]
    assert deny.headers["location"].startswith(REDIRECT)
    assert not store.codes


def test_consent_requires_session(client, store):
    cid = register(client).json()["client_id"]
    _, challenge = pkce()
    loc = authorize(client, cid, challenge).headers["location"]
    req = parse_qs(urlparse(loc).query)["req"][0]
    client.cookies.clear()
    r = client.post("/oauth/consent", data={"req": req, "csrf": oauth.make_csrf(req, 7), "decision": "allow"})
    assert r.status_code == 303 and r.headers["location"].startswith("/oauth/consent")
    assert not store.codes
