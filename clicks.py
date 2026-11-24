"""Pure helpers that turn request headers into the fields stored for a click.

Nothing here touches the network or a database. Privacy rules in force:
no cookies, no fingerprinting, no raw IP addresses stored, location no finer than city.
"""
import hashlib
import re
from typing import Mapping, Optional
from urllib.parse import urlparse

# ---- Visitor id ------------------------------------------------------------------

def visitor_hash(salt: bytes, ip: str, user_agent: str, short_id: str) -> str:
    """Anonymous visitor id: sha256(daily_salt + ip + user_agent + short_id).

    The salt is random, rotates every UTC day and is deleted after two days, so ids
    cannot be linked across days, and the IP cannot be recovered from stored values.
    Including short_id means the same person has different ids on different links.
    """
    h = hashlib.sha256()
    for part in (salt, ip.encode("utf-8"), user_agent.encode("utf-8"), short_id.encode("utf-8")):
        h.update(part)
        h.update(b"\x00")
    return h.hexdigest()


# ---- Language --------------------------------------------------------------------

_LANG_TAG = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}$")


def parse_language(accept_language: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """First Accept-Language tag -> (language, locale), e.g. 'en-IN,en;q=0.9' -> ('en', 'en-IN')."""
    if not accept_language:
        return None, None
    first = accept_language.split(",", 1)[0].split(";", 1)[0].strip()[:35]
    if not _LANG_TAG.match(first):
        return None, None
    parts = first.split("-")
    language = parts[0].lower()
    locale = "-".join([language] + [p.upper() if len(p) == 2 else p.title() if len(p) == 4 else p for p in parts[1:]])
    return language, locale


# ---- Bots and link previews --------------------------------------------------------

BOT_PATTERNS = [
    # Search engines
    "googlebot", "google-inspectiontool", "storebot-google", "adsbot-google", "mediapartners-google",
    "bingbot", "bingpreview", "msnbot", "yandexbot", "baiduspider", "duckduckbot", "applebot",
    "slurp", "sogou", "exabot", "seznambot", "petalbot", "semrushbot", "ahrefsbot", "mj12bot",
    "dotbot", "bytespider", "gptbot", "claudebot", "ccbot", "amazonbot", "perplexitybot",
    # Link previews and chat apps
    "slackbot", "slack-imgproxy", "facebookexternalhit", "facebot", "meta-externalagent", "twitterbot",
    "linkedinbot", "whatsapp", "telegrambot", "discordbot", "skypeuripreview", "pinterestbot",
    "redditbot", "embedly", "quora link preview", "vkshare", "viber", "line-poker", "tumblr",
    "mastodon", "bluesky", "nuzzel", "flipboard", "outbrain", "pocket",
    # Monitoring, scripts, libraries
    "uptimerobot", "pingdom", "statuscake", "site24x7", "datadog", "newrelic", "headlesschrome",
    "phantomjs", "lighthouse", "curl/", "wget/", "python-requests", "python-urllib", "aiohttp",
    "httpx", "go-http-client", "okhttp", "java/", "libwww-perl", "node-fetch", "axios/",
    "postmanruntime", "insomnia", "apache-httpclient", "scrapy", "http_request2",
]
_BOT_RE = re.compile("|".join(re.escape(p) for p in BOT_PATTERNS), re.I)
_GENERIC_BOT_RE = re.compile(r"\b(bot|crawler|spider|crawling|preview|fetcher)\b", re.I)


def is_bot_user_agent(user_agent: Optional[str]) -> bool:
    if not user_agent or user_agent == "Unknown":
        return False
    return bool(_BOT_RE.search(user_agent) or _GENERIC_BOT_RE.search(user_agent))


# ---- Campaign tags -----------------------------------------------------------------

MAX_TAG_LEN = 100
_UTM_KEYS = {
    "utm_source": ("utm_source", "src", "ref", "source"),
    "utm_medium": ("utm_medium",),
    "utm_campaign": ("utm_campaign",),
}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _clean_tag(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = _CONTROL.sub("", value).strip()[:MAX_TAG_LEN]
    return v or None


def extract_utm(query: Mapping[str, str]) -> dict:
    """utm_source/medium/campaign from the short link's query string. `src`, `ref` and
    `source` count as utm_source. Values are trimmed to 100 characters."""
    lowered = {k.lower(): v for k, v in query.items()}
    out = {}
    for field, keys in _UTM_KEYS.items():
        out[field] = next((t for k in keys if (t := _clean_tag(lowered.get(k)))), None)
    return out


# ---- Referrers ---------------------------------------------------------------------

# (host or domain suffix, friendly name). Matches the host itself or any subdomain.
_SOURCE_DOMAINS = [
    ("lnkd.in", "LinkedIn"), ("linkedin.com", "LinkedIn"),
    ("t.co", "X"), ("x.com", "X"), ("twitter.com", "X"),
    ("l.instagram.com", "Instagram"), ("instagram.com", "Instagram"),
    ("facebook.com", "Facebook"), ("fb.com", "Facebook"), ("fb.me", "Facebook"), ("fb.watch", "Facebook"),
    ("youtube.com", "YouTube"), ("youtu.be", "YouTube"),
    ("reddit.com", "Reddit"), ("redd.it", "Reddit"),
    ("bing.com", "Bing"), ("duckduckgo.com", "DuckDuckGo"),
    ("whatsapp.com", "WhatsApp"), ("wa.me", "WhatsApp"),
    ("t.me", "Telegram"), ("telegram.org", "Telegram"), ("web.telegram.org", "Telegram"),
    ("github.com", "GitHub"),
    ("news.ycombinator.com", "Hacker News"),
]
_GOOGLE_RE = re.compile(r"(^|\.)google\.[a-z]{2,3}(\.[a-z]{2})?$")


def referrer_info(referer: Optional[str]) -> tuple[Optional[str], str]:
    """Referer header -> (host, friendly source). No referrer gives (None, 'Direct')."""
    if not referer or referer == "Direct":
        return None, "Direct"
    raw = referer if "://" in referer else f"//{referer}"
    try:
        host = (urlparse(raw).hostname or "").lower()
    except ValueError:
        host = ""
    if not host:
        return None, "Direct"
    host = host[4:] if host.startswith("www.") else host
    if _GOOGLE_RE.search(host):
        return host, "Google"
    for domain, name in _SOURCE_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return host, name
    return host, host


def referer_origin(referer: Optional[str]) -> str:
    """The Referer reduced to scheme and host: paths and query strings can carry personal data."""
    if not referer:
        return "Direct"
    try:
        p = urlparse(referer)
    except ValueError:
        return "Direct"
    if p.scheme in ("http", "https") and p.hostname:
        return f"{p.scheme}://{p.hostname}"
    return "Direct"
