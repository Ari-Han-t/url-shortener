"""Link creation, editing and deletion, shared by the HTTP API and the MCP server."""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple, Optional

import psycopg2
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

logger = logging.getLogger(__name__)

# Aliases that would collide with API routes or the frontend.
RESERVED_ALIASES = {
    "privacy", "terms", "cookies", "disclaimer", "dashboard", "register", "token",
    "shorten", "analytics", "qrcode", "health", "static", "mcp", "api-keys", "links", "oauth", ".well-known", "connected-apps",
}

MAX_EXPIRY_DAYS = 365 * 5
MAX_CACHE_TTL = 3600


# ---- Expiry helpers (pure) ---------------------------------------------------

def as_utc(ts: datetime) -> datetime:
    """Naive datetimes are treated as UTC."""
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def resolve_expiry(
    expires_at: Optional[datetime] = None,
    expires_in_days: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """Validate an expiry and return it as an aware UTC datetime (None means no expiry).

    Give either an absolute time or a number of days, not both. The time must be in
    the future and at most five years away. Raises ValueError otherwise.
    """
    now = as_utc(now) if now else datetime.now(timezone.utc)
    if expires_at is not None and expires_in_days is not None:
        raise ValueError("Use either expires_at or expires_in_days, not both.")
    if expires_in_days is not None:
        if not 1 <= expires_in_days <= 3650:
            raise ValueError("expires_in_days must be between 1 and 3650.")
        return now + timedelta(days=expires_in_days)
    if expires_at is None:
        return None
    when = as_utc(expires_at)
    if when <= now:
        raise ValueError("The expiry must be in the future.")
    if when > now + timedelta(days=MAX_EXPIRY_DAYS):
        raise ValueError("The expiry can be at most 5 years from now.")
    return when


def is_expired(expires_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    if expires_at is None:
        return False
    return as_utc(expires_at) <= (as_utc(now) if now else datetime.now(timezone.utc))


def cache_ttl(expires_at: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    """Seconds to cache a redirect: min(1 hour, time until expiry). None means do not cache."""
    if expires_at is None:
        return MAX_CACHE_TTL
    now = as_utc(now) if now else datetime.now(timezone.utc)
    remaining = (as_utc(expires_at) - now).total_seconds()
    if remaining < 1:
        return None
    return min(MAX_CACHE_TTL, int(remaining))


# ---- Models --------------------------------------------------------------------

def _check_http(v):
    if v.scheme not in ("http", "https"):
        raise ValueError("Only HTTP and HTTPS URLs are allowed")
    return v


class URLCreate(BaseModel):
    long_url: HttpUrl
    custom_id: Optional[str] = Field(default=None, pattern="^[a-zA-Z0-9_-]+$")
    expires_at: Optional[datetime] = None
    expires_in_days: Optional[int] = None

    @field_validator("long_url")
    @classmethod
    def check_scheme(cls, v):
        return _check_http(v)

    @model_validator(mode="after")
    def check_expiry(self):
        resolve_expiry(self.expires_at, self.expires_in_days)  # raises ValueError on bad input
        return self


class LinkUpdate(BaseModel):
    """Fields left out are unchanged. `expires_at: null` removes the expiry."""
    long_url: Optional[HttpUrl] = None
    expires_at: Optional[datetime] = None

    @field_validator("long_url")
    @classmethod
    def check_scheme(cls, v):
        return _check_http(v) if v is not None else v

    @model_validator(mode="after")
    def check_expiry(self):
        if self.expires_at is not None:
            resolve_expiry(self.expires_at)
        return self


class LinkError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class CreatedLink(NamedTuple):
    short_id: str
    long_url: str
    already_existed: bool
    expires_at: Optional[datetime] = None


# ---- Cache ---------------------------------------------------------------------

def purge_cache(short_id: str) -> None:
    """Drop the cached redirect so edits and deletes apply immediately."""
    from database import redis_client  # imported here so the pure helpers need no services

    try:
        redis_client.delete(short_id)
    except Exception as e:
        logger.error(f"Could not purge cache for {short_id}: {e}")


# ---- Operations ----------------------------------------------------------------

def create_short_link(conn, user_id: int, url: URLCreate) -> CreatedLink:
    """Create (or reuse) a short link for a user. Raises LinkError on rule violations."""
    cursor = conn.cursor()
    url_str = str(url.long_url)
    expires_at = resolve_expiry(url.expires_at, url.expires_in_days)

    # Reuse an existing link only when nothing new was asked for and it still works.
    if not url.custom_id and expires_at is None:
        cursor.execute(
            "SELECT short_id, expires_at FROM urls WHERE long_url = %s AND user_id = %s ORDER BY id",
            (url_str, user_id),
        )
        for sid, exp in cursor.fetchall():
            if not is_expired(exp):
                return CreatedLink(sid, url_str, True, exp)

    if url.custom_id:
        if url.custom_id.lower() in RESERVED_ALIASES:
            raise LinkError(400, "That custom alias is reserved.")
        cursor.execute("SELECT short_id FROM urls WHERE short_id = %s", (url.custom_id,))
        if cursor.fetchone():
            raise LinkError(400, "That custom alias is already taken!")
        short_id = url.custom_id
    else:
        while True:
            short_id = secrets.token_urlsafe(8)
            cursor.execute("SELECT short_id FROM urls WHERE short_id = %s", (short_id,))
            if cursor.fetchone() is None:
                break

    try:
        cursor.execute(
            "INSERT INTO urls (short_id, long_url, user_id, expires_at) VALUES (%s, %s, %s, %s)",
            (short_id, url_str, user_id, expires_at),
        )
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        raise LinkError(400, "Failed to create short URL. Try again.")

    logger.info(f"URL shortened: {short_id} -> {url_str}")
    return CreatedLink(short_id, url_str, False, expires_at)


KEEP: Any = object()  # "leave this field unchanged"


def update_link(conn, user_id: int, short_id: str, long_url: Optional[str] = None, expires_at: Any = KEEP) -> dict:
    """Change the destination and/or expiry of a link the user owns. The alias cannot change.

    `expires_at` is KEEP (unchanged), None (remove expiry) or a validated aware datetime.
    """
    cursor = conn.cursor()
    sets, params = [], []
    if long_url is not None:
        sets.append("long_url = %s")
        params.append(long_url)
    if expires_at is not KEEP:
        sets.append("expires_at = %s")
        params.append(expires_at)
    if not sets:
        raise LinkError(400, "Nothing to update.")
    sets.append("updated_at = CURRENT_TIMESTAMP")
    cursor.execute(
        f"UPDATE urls SET {', '.join(sets)} WHERE short_id = %s AND user_id = %s",
        (*params, short_id, user_id),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        raise LinkError(404, "Link not found or you don't own it.")
    conn.commit()
    purge_cache(short_id)
    return get_link(conn, user_id, short_id)


def delete_link(conn, user_id: int, short_id: str) -> None:
    """Delete a link the user owns together with its click history."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM urls WHERE short_id = %s AND user_id = %s", (short_id, user_id))
    if not cursor.fetchone():
        raise LinkError(404, "Link not found or you don't own it.")
    cursor.execute("DELETE FROM click_events WHERE short_id = %s", (short_id,))
    cursor.execute("DELETE FROM urls WHERE short_id = %s AND user_id = %s", (short_id, user_id))
    conn.commit()
    purge_cache(short_id)


LINK_COLUMNS = "short_id, long_url, clicks, created_at, expires_at, updated_at"


def link_dict(row: tuple) -> dict:
    """Row order: LINK_COLUMNS."""
    from analytics_utils import iso_utc

    return {
        "short_id": row[0],
        "long_url": row[1],
        "clicks": row[2] or 0,
        "created_at": iso_utc(row[3]) or None,
        "expires_at": iso_utc(row[4]) or None,
        "updated_at": iso_utc(row[5]) or None,
        "expired": is_expired(row[4]),
    }


def get_link(conn, user_id: int, short_id: str) -> dict:
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {LINK_COLUMNS} FROM urls WHERE short_id = %s AND user_id = %s", (short_id, user_id)
    )
    row = cursor.fetchone()
    if not row:
        raise LinkError(404, "Link not found or you don't own it.")
    return link_dict(row)
