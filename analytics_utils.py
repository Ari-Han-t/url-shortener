"""Pure helpers (no database or network) shared by the API and the MCP server."""
import csv
import hashlib
import io
import secrets
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Iterator, Optional
from urllib.parse import urlparse

API_KEY_PREFIX = "hop_"
KEY_PREFIX_DISPLAY_LEN = 8
EXPORT_COLUMNS = [
    "timestamp", "device_type", "os", "browser", "referer", "visitor_id",
    "country_code", "country", "region", "city", "language", "is_bot",
    "utm_source", "utm_medium", "utm_campaign", "referrer_host", "referrer_source",
]
# Column order of the SELECT used for exports and recent clicks.
CLICK_SELECT = (
    "timestamp, device_type, os, browser, referer, visitor_id, country_code, country, region, city, "
    "language, is_bot, utm_source, utm_medium, utm_campaign, referrer_host, referrer_source"
)

_FORMULA_CHARS = ("=", "+", "-", "@")


# ---- API keys -------------------------------------------------------------

def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_display_prefix(key: str) -> str:
    return key[:KEY_PREFIX_DISPLAY_LEN]


def looks_like_api_key(value: str) -> bool:
    return value.startswith(API_KEY_PREFIX) and 20 <= len(value) <= 200


# ---- CSV export -----------------------------------------------------------

def csv_safe(value: Any) -> str:
    """Neutralise spreadsheet formula injection by prefixing a single quote."""
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_CHARS) or text.startswith(("\t", "\r")):
        return "'" + text
    return text


def iso_utc(ts: Optional[datetime]) -> str:
    """ISO 8601 UTC. The database stores naive UTC timestamps."""
    if ts is None:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def click_record(row: tuple) -> dict:
    """Row order: CLICK_SELECT. Old rows have NULLs for the newer fields."""
    def opt(v):
        return v if v is not None else ""

    return {
        "timestamp": iso_utc(row[0]),
        "device_type": row[1] or "Unknown",
        "os": row[2] or "Unknown",
        "browser": row[3] or "Unknown",
        "referer": row[4] or "Direct",
        "visitor_id": opt(row[5]),
        "country_code": opt(row[6]),
        "country": opt(row[7]),
        "region": opt(row[8]),
        "city": opt(row[9]),
        "language": opt(row[10]),
        "is_bot": bool(row[11]),
        "utm_source": opt(row[12]),
        "utm_medium": opt(row[13]),
        "utm_campaign": opt(row[14]),
        "referrer_host": opt(row[15]),
        "referrer_source": opt(row[16]),
    }


def csv_chunks(records: Iterable[dict]) -> Iterator[str]:
    """Yield CSV text in small chunks so large exports are not built in memory."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(EXPORT_COLUMNS)
    for rec in records:
        writer.writerow([csv_safe(str(rec[c]).lower() if isinstance(rec[c], bool) else rec[c]) for c in EXPORT_COLUMNS])
        if buf.tell() > 16384:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)
    yield buf.getvalue()


# ---- Aggregation ----------------------------------------------------------

def _as_utc_date(ts: datetime) -> date:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).date()


def clicks_per_day(timestamps: Iterable[Optional[datetime]], days: int, today: Optional[date] = None) -> list[dict]:
    """Click counts for each UTC day in the window ending today, oldest first, zeros included."""
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    counts: Counter = Counter()
    for ts in timestamps:
        if ts is None:
            continue
        d = _as_utc_date(ts)
        if start <= d <= today:
            counts[d] += 1
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "clicks": counts[start + timedelta(days=i)]}
        for i in range(days)
    ]


def top_counts(values: Iterable[Optional[str]], limit: int = 5, default: str = "Unknown") -> list[dict]:
    counts = Counter((v or default) for v in values)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"name": k, "clicks": n} for k, n in ranked[:limit]]


def referrer_host(referer: Optional[str]) -> str:
    if not referer or referer == "Direct":
        return "Direct"
    host = urlparse(referer).netloc
    return host or referer


def week_over_week(timestamps: Iterable[Optional[datetime]], now: Optional[datetime] = None) -> dict:
    """Clicks in the last 7 days versus the 7 days before that."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    last_start = now - timedelta(days=7)
    prev_start = now - timedelta(days=14)
    last = prev = 0
    for ts in timestamps:
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= last_start:
            last += 1
        elif ts >= prev_start:
            prev += 1
    return {"last_7_days": last, "previous_7_days": prev}
