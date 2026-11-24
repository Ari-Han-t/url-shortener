import os

import pytest

import clicks
import geo


# ---- visitor hash -------------------------------------------------------------

def test_visitor_hash_depends_on_every_input():
    base = clicks.visitor_hash(b"salt-1", "1.2.3.4", "UA", "abc")
    assert len(base) == 64
    assert base == clicks.visitor_hash(b"salt-1", "1.2.3.4", "UA", "abc")
    assert base != clicks.visitor_hash(b"salt-2", "1.2.3.4", "UA", "abc")  # daily salt rotation
    assert base != clicks.visitor_hash(b"salt-1", "1.2.3.5", "UA", "abc")
    assert base != clicks.visitor_hash(b"salt-1", "1.2.3.4", "UA2", "abc")
    assert base != clicks.visitor_hash(b"salt-1", "1.2.3.4", "UA", "other")


def test_visitor_hash_has_no_field_boundary_collisions():
    assert clicks.visitor_hash(b"s", "1.2.3.4", "ab", "c") != clicks.visitor_hash(b"s", "1.2.3.4", "a", "bc")


def test_visitor_hash_does_not_contain_the_ip():
    assert "8.8.8.8" not in clicks.visitor_hash(b"s", "8.8.8.8", "UA", "abc")


# ---- language -------------------------------------------------------------------

@pytest.mark.parametrize("header,expected", [
    ("en-IN,en;q=0.9,hi;q=0.8", ("en", "en-IN")),
    ("en-us", ("en", "en-US")),
    ("fr", ("fr", "fr")),
    ("zh-Hant-TW,zh;q=0.9", ("zh", "zh-Hant-TW")),
    ("*", (None, None)),
    ("", (None, None)),
    (None, (None, None)),
    ("<script>alert(1)</script>", (None, None)),
    ("x" * 500, (None, None)),
])
def test_parse_language(header, expected):
    assert clicks.parse_language(header) == expected


# ---- bots -------------------------------------------------------------------------

@pytest.mark.parametrize("ua", [
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Twitterbot/1.0",
    "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)",
    "WhatsApp/2.23.20.0 A",
    "TelegramBot (like TwitterBot)",
    "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
    "curl/8.4.0",
    "python-requests/2.31.0",
    "SomeNewCrawler/1.0 crawler",
])
def test_bots_detected(ua):
    assert clicks.is_bot_user_agent(ua)


@pytest.mark.parametrize("ua", [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Unknown", "", None,
])
def test_humans_not_flagged(ua):
    assert not clicks.is_bot_user_agent(ua)


# ---- utm --------------------------------------------------------------------------

def test_extract_utm_full():
    q = {"utm_source": "newsletter", "utm_medium": "email", "utm_campaign": "spring", "x": "1"}
    assert clicks.extract_utm(q) == {"utm_source": "newsletter", "utm_medium": "email", "utm_campaign": "spring"}


def test_extract_utm_aliases_and_precedence():
    assert clicks.extract_utm({"src": "twitter"})["utm_source"] == "twitter"
    assert clicks.extract_utm({"ref": "hn"})["utm_source"] == "hn"
    assert clicks.extract_utm({"src": "a", "utm_source": "b"})["utm_source"] == "b"


def test_extract_utm_truncates_and_cleans():
    out = clicks.extract_utm({"utm_campaign": "x" * 300, "utm_source": "  \x00 ", "utm_medium": "a\nb"})
    assert len(out["utm_campaign"]) == 100
    assert out["utm_source"] is None
    assert out["utm_medium"] == "ab"


def test_extract_utm_empty():
    assert clicks.extract_utm({}) == {"utm_source": None, "utm_medium": None, "utm_campaign": None}


# ---- referrers ----------------------------------------------------------------------

@pytest.mark.parametrize("referer,expected", [
    (None, (None, "Direct")),
    ("Direct", (None, "Direct")),
    ("", (None, "Direct")),
    ("https://lnkd.in/abc", ("lnkd.in", "LinkedIn")),
    ("https://www.linkedin.com/feed/", ("linkedin.com", "LinkedIn")),
    ("https://t.co/xyz", ("t.co", "X")),
    ("https://x.com/a/status/1", ("x.com", "X")),
    ("https://twitter.com/", ("twitter.com", "X")),
    ("https://l.instagram.com/?u=1", ("l.instagram.com", "Instagram")),
    ("https://l.facebook.com/l.php", ("l.facebook.com", "Facebook")),
    ("https://m.facebook.com/", ("m.facebook.com", "Facebook")),
    ("https://www.youtube.com/watch", ("youtube.com", "YouTube")),
    ("https://old.reddit.com/r/x", ("old.reddit.com", "Reddit")),
    ("https://www.google.co.in/", ("google.co.in", "Google")),
    ("https://www.google.com/search?q=x", ("google.com", "Google")),
    ("https://www.bing.com/", ("bing.com", "Bing")),
    ("https://duckduckgo.com/", ("duckduckgo.com", "DuckDuckGo")),
    ("https://web.whatsapp.com/", ("web.whatsapp.com", "WhatsApp")),
    ("https://t.me/chan", ("t.me", "Telegram")),
    ("https://github.com/a/b", ("github.com", "GitHub")),
    ("https://news.ycombinator.com/item?id=1", ("news.ycombinator.com", "Hacker News")),
    ("https://blog.example.org/post", ("blog.example.org", "blog.example.org")),
    ("https://notgoogle.com/", ("notgoogle.com", "notgoogle.com")),
    ("https://evilt.co/", ("evilt.co", "evilt.co")),
])
def test_referrer_info(referer, expected):
    assert clicks.referrer_info(referer) == expected


def test_referer_origin_drops_path_and_query():
    assert clicks.referer_origin("https://example.com/a/b?email=me@x.com#h") == "https://example.com"
    assert clicks.referer_origin(None) == "Direct"
    assert clicks.referer_origin("android-app://com.google.android.gm") == "Direct"


# ---- geo (needs the DB-IP file; skipped when it is absent) ----------------------------

HAVE_DB = os.path.isfile(geo.db_path())


@pytest.mark.skipif(not HAVE_DB, reason="DB-IP database not downloaded (scripts/update_geoip.sh)")
def test_geo_lookup_known_public_ips():
    g = geo.lookup("8.8.8.8")
    assert g["country_code"] == "US" and g["country"] == "United States"
    assert g["region"] and g["city"]
    assert geo.lookup("1.1.1.1")["country_code"] == "AU"
    assert set(g) == {"country_code", "country", "region", "city"}  # no coordinates


@pytest.mark.skipif(not HAVE_DB, reason="DB-IP database not downloaded")
def test_geo_lookup_private_and_invalid_are_empty():
    for ip in ("127.0.0.1", "10.0.0.1", "not-an-ip", "", None):
        assert geo.lookup(ip) == geo.EMPTY


def test_geo_missing_file_returns_empty(tmp_path):
    assert geo.lookup("8.8.8.8", path=str(tmp_path / "nope.mmdb")) == geo.EMPTY
