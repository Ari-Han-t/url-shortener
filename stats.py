"""SQL aggregations over click_events, shared by the HTTP API and the MCP server.

Bot and link-preview hits (is_bot) are excluded everywhere except `bot_hits`.
Unique visitors are counted per day: visitor ids rotate daily, so the same person
on two different days counts twice.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

NOT_BOT = "is_bot IS NOT TRUE"

_SOURCE_EXPR = (
    "COALESCE(referrer_source, CASE WHEN referer IS NULL OR referer = 'Direct' THEN 'Direct' ELSE 'Unknown' END)"
)
_CAMPAIGN_EXPR = "NULLIF(CONCAT_WS(' / ', utm_source, utm_medium, utm_campaign), '')"

# dimension -> (grouping expression, extra WHERE, label expression or None).
# These are fixed strings; user input only ever selects a key, never reaches the SQL.
DIMENSIONS: dict[str, tuple[str, Optional[str], Optional[str]]] = {
    "country": ("COALESCE(country_code, 'Unknown')", None, "MAX(country)"),
    "city": ("COALESCE(city || ', ' || country_code, 'Unknown')", None, None),
    "language": ("COALESCE(language, 'Unknown')", None, None),
    "source": (_SOURCE_EXPR, None, None),
    "campaign": (_CAMPAIGN_EXPR, f"{_CAMPAIGN_EXPR} IS NOT NULL", None),
    "device": ("COALESCE(device_type, 'Unknown')", None, None),
    "os": ("COALESCE(os, 'Unknown')", None, None),
    "browser": ("COALESCE(browser, 'Unknown')", None, None),
}


def window_start(days: Optional[int]) -> Optional[datetime]:
    """Naive UTC start of a window (click timestamps are stored as naive UTC)."""
    if days is None:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None)


def _scope(scope_sql: str, params: list, days: Optional[int]) -> tuple[str, list]:
    where = f"({scope_sql})"
    params = list(params)
    start = window_start(days)
    if start is not None:
        where += " AND timestamp >= %s"
        params.append(start)
    return where, params


def link_scope(short_id: str) -> tuple[str, list]:
    return "short_id = %s", [short_id]


def account_scope(user_id: int) -> tuple[str, list]:
    return "short_id IN (SELECT short_id FROM urls WHERE user_id = %s)", [user_id]


def top(cur, scope_sql: str, params: list, dimension: str, days: Optional[int] = None, limit: int = 10) -> list[dict]:
    if dimension not in DIMENSIONS:
        raise ValueError(f"dimension must be one of: {', '.join(sorted(DIMENSIONS))}")
    key_expr, extra, label_expr = DIMENSIONS[dimension]
    where, p = _scope(scope_sql, params, days)
    where += f" AND {NOT_BOT}" + (f" AND {extra}" if extra else "")
    label_sql = label_expr or "NULL"
    cur.execute(
        f"SELECT {key_expr} AS k, {label_sql}, COUNT(*) AS n FROM click_events WHERE {where} "
        "GROUP BY k ORDER BY n DESC, k LIMIT %s",
        (*p, limit),
    )
    rows = []
    for k, label, n in cur.fetchall():
        row = {"name": k, "clicks": n}
        if label:
            row["label"] = label
        rows.append(row)
    return rows


def unique_visitors(cur, scope_sql: str, params: list, days: Optional[int] = None) -> int:
    where, p = _scope(scope_sql, params, days)
    cur.execute(
        "SELECT COUNT(DISTINCT (timestamp::date, visitor_id)) FILTER (WHERE visitor_id IS NOT NULL) "
        f"FROM click_events WHERE {where} AND {NOT_BOT}",
        p,
    )
    return cur.fetchone()[0] or 0


def bot_hits(cur, scope_sql: str, params: list, days: Optional[int] = None) -> int:
    where, p = _scope(scope_sql, params, days)
    cur.execute(f"SELECT COUNT(*) FROM click_events WHERE {where} AND is_bot IS TRUE", p)
    return cur.fetchone()[0] or 0


def summary(cur, scope_sql: str, params: list, days: Optional[int] = None, limit: int = 10) -> dict:
    """Unique visitors, bot hits and the top places, languages, sources and campaigns."""
    return {
        "unique_visitors": unique_visitors(cur, scope_sql, params, days),
        "bot_hits": bot_hits(cur, scope_sql, params, days),
        "countries": top(cur, scope_sql, params, "country", days, limit),
        "cities": top(cur, scope_sql, params, "city", days, limit),
        "languages": top(cur, scope_sql, params, "language", days, limit),
        "sources": top(cur, scope_sql, params, "source", days, limit),
        "campaigns": top(cur, scope_sql, params, "campaign", days, limit),
    }
