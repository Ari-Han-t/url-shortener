from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import links
import main
from database import get_db

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_resolve_expiry_none_and_days():
    assert links.resolve_expiry(now=NOW) is None
    assert links.resolve_expiry(expires_in_days=7, now=NOW) == NOW + timedelta(days=7)


@pytest.mark.parametrize("days", [0, -1, 3651])
def test_resolve_expiry_rejects_bad_days(days):
    with pytest.raises(ValueError):
        links.resolve_expiry(expires_in_days=days, now=NOW)


def test_resolve_expiry_absolute_rules():
    assert links.resolve_expiry(NOW + timedelta(hours=1), now=NOW) == NOW + timedelta(hours=1)
    with pytest.raises(ValueError):
        links.resolve_expiry(NOW - timedelta(seconds=1), now=NOW)
    with pytest.raises(ValueError):
        links.resolve_expiry(NOW + timedelta(days=365 * 5 + 1), now=NOW)
    with pytest.raises(ValueError):
        links.resolve_expiry(NOW + timedelta(days=1), 3, now=NOW)


def test_naive_datetimes_are_utc():
    naive = (NOW + timedelta(days=1)).replace(tzinfo=None)
    assert links.resolve_expiry(naive, now=NOW).tzinfo is not None


def test_is_expired():
    assert not links.is_expired(None, NOW)
    assert links.is_expired(NOW, NOW)
    assert not links.is_expired(NOW + timedelta(seconds=1), NOW)


def test_cache_ttl():
    assert links.cache_ttl(None, NOW) == 3600
    assert links.cache_ttl(NOW + timedelta(days=2), NOW) == 3600
    assert links.cache_ttl(NOW + timedelta(seconds=90), NOW) == 90
    assert links.cache_ttl(NOW - timedelta(seconds=5), NOW) is None
    assert links.cache_ttl(NOW + timedelta(milliseconds=200), NOW) is None


def test_models_validate_expiry():
    with pytest.raises(ValueError):
        links.URLCreate(long_url="https://example.com", expires_in_days=0)
    with pytest.raises(ValueError):
        links.LinkUpdate(expires_at=NOW - timedelta(days=1))
    assert links.LinkUpdate(expires_at=None).expires_at is None
    with pytest.raises(ValueError):
        links.LinkUpdate(long_url="ftp://example.com/x")


def test_links_alias_reserved():
    assert "links" in links.RESERVED_ALIASES


def _client_with_row(row):
    conn = mock.MagicMock()
    conn.cursor.return_value.fetchone.return_value = row
    main.app.dependency_overrides[get_db] = lambda: conn
    main.redis_client.get.return_value = None
    return TestClient(main.app, follow_redirects=False)


def test_redirect_expired_returns_410_html_and_caches_nothing():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    try:
        r = _client_with_row(("https://example.com", past)).get("/gone1")
    finally:
        main.app.dependency_overrides.clear()
    assert r.status_code == 410
    assert "text/html" in r.headers["content-type"]
    assert "This link has expired" in r.text
    main.redis_client.setex.assert_not_called()


def test_redirect_unknown_returns_404_html():
    try:
        r = _client_with_row(None).get("/nope1")
    finally:
        main.app.dependency_overrides.clear()
    assert r.status_code == 404
    assert "Link not found" in r.text


def test_redirect_caches_with_short_ttl_before_expiry():
    soon = datetime.now(timezone.utc) + timedelta(seconds=120)
    main.redis_client.setex.reset_mock()
    try:
        r = _client_with_row(("https://example.com", soon)).get("/soon1")
    finally:
        main.app.dependency_overrides.clear()
    assert r.status_code == 307
    ttl = main.redis_client.setex.call_args[0][1]
    assert 100 <= ttl <= 120
