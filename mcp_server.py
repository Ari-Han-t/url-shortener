"""MCP server (Streamable HTTP) exposing a user's link analytics to Claude.

Mounted in main.py at /mcp. Authentication: `Authorization: Bearer hop_...`
(personal API key). All user resolution goes through `resolve_principal`, so
other credential types can be added there later.
"""
import contextlib
import hmac
import logging
import os
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Iterator, NamedTuple, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

import analytics_utils as au
import oauth
import stats
from database import db_pool, redis_client
from links import KEEP, LINK_COLUMNS, LinkError, URLCreate, create_short_link, link_dict, resolve_expiry, update_link

logger = logging.getLogger(__name__)

MCP_RATE_LIMIT_PER_MINUTE = 60
MAX_RECENT_CLICKS = 500


class Principal(NamedTuple):
    user_id: int
    key_id: Optional[int]  # rate limit identity: API key id, or OAuth token row id
    source: str = "api_key"  # "api_key" or "oauth"


_principal: ContextVar[Optional[Principal]] = ContextVar("hop_principal", default=None)


def public_base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "").rstrip("/")


def short_url(short_id: str) -> str:
    return f"{public_base_url()}/{short_id}"


@contextlib.contextmanager
def db_conn() -> Iterator:
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        with contextlib.suppress(Exception):
            conn.rollback()
        db_pool.putconn(conn)


# ---- Authentication -------------------------------------------------------

def resolve_principal(token: str) -> Optional[Principal]:
    """Map a bearer token to a user: a hop_ API key or an OAuth access token.
    The only place that decides who is calling."""
    if au.looks_like_api_key(token):
        return _resolve_api_key(token)
    if token.startswith("hopat_"):
        row = oauth.lookup_access_token(token)
        if row:
            return Principal(user_id=row["user_id"], key_id=row["id"], source="oauth")
    return None


def _resolve_api_key(key: str) -> Optional[Principal]:
    digest = au.hash_api_key(key)
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, key_hash FROM api_keys WHERE key_hash = %s AND revoked_at IS NULL",
            (digest,),
        )
        row = cur.fetchone()
        if not row or not hmac.compare_digest(row[2], digest):
            return None
        cur.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = %s", (row[0],))
        conn.commit()
        return Principal(user_id=row[1], key_id=row[0])


def _rate_limited(principal: Principal) -> bool:
    """Fixed-window counter in Redis. Fails open if Redis is unavailable."""
    window = int(datetime.now(timezone.utc).timestamp() // 60)
    ident = f"{principal.source}-{principal.key_id}" if principal.key_id else f"user-{principal.user_id}"
    key = f"mcp-rate:{ident}:{window}"
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, 90)
        return count > MCP_RATE_LIMIT_PER_MINUTE
    except Exception as e:  # pragma: no cover
        logger.error(f"MCP rate limit check failed: {e}")
        return False


class MCPAuthMiddleware:
    """ASGI wrapper: authenticates, rate limits, then hands the request to the MCP app."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        auth = headers.get("authorization", "")
        token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""

        principal = None
        if token:
            principal = await run_in_threadpool(resolve_principal, token)
        if principal is None:
            # RFC 9728: tell clients where to find the protected resource metadata, so they can start OAuth.
            origin = oauth.public_origin(headers, scope.get("scheme", "http"))
            challenge = f'Bearer realm="hop", resource_metadata="{oauth.resource_metadata_url(origin)}"'
            if token:
                challenge += ', error="invalid_token"'
            resp = JSONResponse(
                {"success": False, "message": "Missing, invalid or revoked credentials. Use an API key or sign in with OAuth."},
                status_code=401,
                headers={"WWW-Authenticate": challenge},
            )
            await resp(scope, receive, send)
            return

        if await run_in_threadpool(_rate_limited, principal):
            resp = JSONResponse(
                {"success": False, "message": "Too many requests. Wait a minute and try again."},
                status_code=429,
                headers={"Retry-After": "60"},
            )
            await resp(scope, receive, send)
            return

        reset = _principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            _principal.reset(reset)


# ---- Tools ----------------------------------------------------------------

mcp = FastMCP(
    "hop",
    instructions=(
        "hop is a URL shortener with click analytics. These tools read and create the "
        "links of the user who owns the API key."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _user_id() -> int:
    p = _principal.get()
    if p is None:
        raise RuntimeError("Not authenticated")
    return p.user_id


def _owned_link(cur, user_id: int, short_id: str):
    cur.execute(
        "SELECT clicks, long_url, created_at FROM urls WHERE short_id = %s AND user_id = %s",
        (short_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"No link with short_id '{short_id}' in this account.")
    return row


@mcp.tool()
def list_links() -> list[dict]:
    """List all of the user's short links with click totals, creation time and expiry
    (expires_at is null when the link never expires; expired is true once it has passed)."""
    uid = _user_id()
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {LINK_COLUMNS} FROM urls WHERE user_id = %s ORDER BY created_at DESC",
            (uid,),
        )
        out = []
        for r in cur.fetchall():
            d = link_dict(r)
            out.append({**d, "short_url": short_url(d["short_id"])})
        return out


@mcp.tool()
def link_analytics(short_id: str, days: int = 30) -> dict:
    """Analytics for one link over the last `days` days (1-365, UTC): total clicks, unique visitors
    (counted per day), clicks per day, and the top devices, operating systems, browsers, countries,
    cities, languages, traffic sources and campaign tags. Bots and link-preview fetches are
    excluded from every count and reported separately as bot_hits."""
    days = max(1, min(int(days), 365))
    uid = _user_id()
    with db_conn() as conn:
        cur = conn.cursor()
        total, long_url, created_at = _owned_link(cur, uid, short_id)
        cur.execute(
            f"SELECT timestamp, device_type, os, browser FROM click_events "
            f"WHERE short_id = %s AND timestamp >= %s AND {stats.NOT_BOT}",
            (short_id, stats.window_start(days)),
        )
        rows = cur.fetchall()
        scope_sql, scope_params = stats.link_scope(short_id)
        summ = stats.summary(cur, scope_sql, scope_params, days=days, limit=10)
    return {
        "short_id": short_id,
        "short_url": short_url(short_id),
        "long_url": long_url,
        "created_at": au.iso_utc(created_at),
        "total_clicks_all_time": total,
        "window_days": days,
        "clicks_in_window": len(rows),
        "unique_visitors": summ["unique_visitors"],
        "bot_hits": summ["bot_hits"],
        "clicks_per_day": au.clicks_per_day([r[0] for r in rows], days),
        "top_devices": au.top_counts((r[1] for r in rows), limit=5),
        "top_operating_systems": au.top_counts((r[2] for r in rows), limit=5),
        "top_browsers": au.top_counts((r[3] for r in rows), limit=5),
        "top_countries": summ["countries"],
        "top_cities": summ["cities"],
        "top_languages": summ["languages"],
        "top_sources": summ["sources"],
        "top_campaigns": summ["campaigns"],
    }


@mcp.tool()
def clicks_by(short_id: str, dimension: str, days: int = 30) -> list[dict]:
    """Click counts for one link grouped by a single dimension over the last `days` days (1-365).
    dimension is one of: country, city, language, source, campaign, device, os, browser.
    'source' groups referrers into names like LinkedIn or Google; 'campaign' groups utm tags.
    Bots and link previews are excluded."""
    days = max(1, min(int(days), 365))
    if dimension not in stats.DIMENSIONS:
        raise ValueError(f"dimension must be one of: {', '.join(sorted(stats.DIMENSIONS))}")
    uid = _user_id()
    with db_conn() as conn:
        cur = conn.cursor()
        _owned_link(cur, uid, short_id)
        scope_sql, scope_params = stats.link_scope(short_id)
        return stats.top(cur, scope_sql, scope_params, dimension, days=days, limit=25)


@mcp.tool()
def recent_clicks(short_id: str, limit: int = 50) -> list[dict]:
    """The most recent human clicks on a link, newest first (limit 1-500), with location (city level),
    source and campaign tags. Visitor ids are anonymous daily hashes; bots are excluded."""
    limit = max(1, min(int(limit), MAX_RECENT_CLICKS))
    uid = _user_id()
    with db_conn() as conn:
        cur = conn.cursor()
        _owned_link(cur, uid, short_id)
        cur.execute(
            f"SELECT {au.CLICK_SELECT} FROM click_events "
            f"WHERE short_id = %s AND {stats.NOT_BOT} ORDER BY timestamp DESC LIMIT %s",
            (short_id, limit),
        )
        return [au.click_record(r) for r in cur.fetchall()]


@mcp.tool()
def account_summary() -> dict:
    """Account overview: number of links, total clicks (bots excluded), the top 5 links by clicks,
    clicks in the last 7 days compared with the 7 days before, and over the last 30 days the unique
    visitors, top countries, traffic sources and campaigns, plus bot/preview hits."""
    uid = _user_id()
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT short_id, long_url, clicks FROM urls WHERE user_id = %s ORDER BY clicks DESC, short_id",
            (uid,),
        )
        links = cur.fetchall()
        cur.execute(
            "SELECT c.timestamp FROM click_events c JOIN urls u ON u.short_id = c.short_id "
            f"WHERE u.user_id = %s AND c.timestamp >= %s AND c.{stats.NOT_BOT}",
            (uid, stats.window_start(14)),
        )
        stamps = [r[0] for r in cur.fetchall()]
        scope_sql, scope_params = stats.account_scope(uid)
        uniq = stats.unique_visitors(cur, scope_sql, scope_params, days=30)
        bots = stats.bot_hits(cur, scope_sql, scope_params, days=30)
        countries = stats.top(cur, scope_sql, scope_params, "country", days=30, limit=5)
        sources = stats.top(cur, scope_sql, scope_params, "source", days=30, limit=5)
        campaigns = stats.top(cur, scope_sql, scope_params, "campaign", days=30, limit=5)
    return {
        "total_links": len(links),
        "total_clicks": sum(r[2] or 0 for r in links),
        "top_links": [
            {"short_id": r[0], "short_url": short_url(r[0]), "long_url": r[1], "clicks": r[2]}
            for r in links[:5]
        ],
        **au.week_over_week(stamps),
        "last_30_days": {
            "unique_visitors": uniq,
            "bot_hits": bots,
            "top_countries": countries,
            "top_sources": sources,
            "top_campaigns": campaigns,
        },
    }


@mcp.tool(name="create_short_link")
def create_short_link_tool(long_url: str, custom_alias: Optional[str] = None, expires_in_days: Optional[int] = None) -> dict:
    """Create a short link for an http(s) URL, optionally with a custom alias (letters, numbers,
    hyphens, underscores). If the user already shortened this URL and no alias is given, the
    existing link is returned. Optionally expire the link after `expires_in_days` days (1-3650)."""
    uid = _user_id()
    try:
        payload = URLCreate(long_url=long_url, custom_id=custom_alias or None, expires_in_days=expires_in_days)
    except ValidationError as e:
        raise ValueError(e.errors()[0]["msg"].removeprefix("Value error, "))
    with db_conn() as conn:
        try:
            created = create_short_link(conn, uid, payload)
        except LinkError as e:
            raise ValueError(e.detail)
    return {
        "short_id": created.short_id,
        "short_url": short_url(created.short_id),
        "long_url": created.long_url,
        "already_existed": created.already_existed,
        "expires_at": au.iso_utc(created.expires_at) or None,
    }


@mcp.tool(name="update_link")
def update_link_tool(
    short_id: str,
    long_url: Optional[str] = None,
    expires_in_days: Optional[int] = None,
    remove_expiry: bool = False,
) -> dict:
    """Change where a link points and/or when it expires. Pass `long_url` to change the
    destination, `expires_in_days` (1-3650) to set an expiry that many days from now, or
    `remove_expiry=true` to make it permanent. The short_id itself cannot be changed."""
    uid = _user_id()
    if remove_expiry and expires_in_days is not None:
        raise ValueError("Use either expires_in_days or remove_expiry, not both.")
    try:
        new_url = None
        if long_url is not None:
            new_url = str(URLCreate(long_url=long_url).long_url)
        expires = KEEP
        if remove_expiry:
            expires = None
        elif expires_in_days is not None:
            expires = resolve_expiry(None, expires_in_days)
    except ValidationError as e:
        raise ValueError(e.errors()[0]["msg"].removeprefix("Value error, "))
    with db_conn() as conn:
        try:
            link = update_link(conn, uid, short_id, new_url, expires)
        except LinkError as e:
            raise ValueError(e.detail)
    return {**link, "short_url": short_url(short_id)}


_inner = mcp.streamable_http_app()  # builds the session manager; route path is "/mcp"
asgi_app: ASGIApp = MCPAuthMiddleware(_inner)


def session_manager():
    """Must be run (`async with session_manager().run()`) in the host app's lifespan."""
    return mcp.session_manager
