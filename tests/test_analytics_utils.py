import csv
import io
from datetime import date, datetime, timezone

import analytics_utils as au


def test_csv_safe_prefixes_formula_cells():
    for bad in ["=1+1", "+cmd", "-2", "@SUM(A1)", "\tx"]:
        assert au.csv_safe(bad) == "'" + bad
    assert au.csv_safe("https://example.com") == "https://example.com"
    assert au.csv_safe(None) == ""


def test_csv_export_roundtrip_and_header():
    rec = {c: "x" for c in au.EXPORT_COLUMNS}
    rec["referer"] = '=HYPERLINK("x")'
    rec["is_bot"] = True
    text = "".join(au.csv_chunks([rec]))
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == au.EXPORT_COLUMNS
    assert "visitor_id" in rows[0] and "ip_hash" not in rows[0]
    assert rows[1][rows[0].index("referer")] == "'=HYPERLINK(\"x\")"
    assert rows[1][rows[0].index("is_bot")] == "true"
    assert len(rows) == 2


def test_click_record_maps_new_fields_and_old_rows():
    old = (datetime(2026, 1, 2), "PC", "Windows", "Chrome") + (None,) * 13
    rec = au.click_record(old)
    assert rec["referer"] == "Direct" and rec["visitor_id"] == "" and rec["is_bot"] is False
    assert set(rec) == set(au.EXPORT_COLUMNS)


def test_csv_export_streams_in_chunks():
    rec = {c: "x" * 50 for c in au.EXPORT_COLUMNS}
    chunks = list(au.csv_chunks(rec for _ in range(1000)))
    assert len(chunks) > 1
    assert len(list(csv.reader(io.StringIO("".join(chunks))))) == 1001


def test_api_key_format_and_hash():
    key = au.generate_api_key()
    assert key.startswith("hop_") and au.looks_like_api_key(key)
    assert au.key_display_prefix(key) == key[:8]
    assert au.hash_api_key(key) == au.hash_api_key(key)
    assert au.hash_api_key(key) != au.hash_api_key(au.generate_api_key())
    assert len(au.hash_api_key(key)) == 64
    assert not au.looks_like_api_key("eyJhbGciOi.jwt.token")


def test_iso_utc_treats_naive_as_utc():
    assert au.iso_utc(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05Z"
    assert au.iso_utc(None) == ""


def test_clicks_per_day_fills_zeros_and_ignores_out_of_window():
    today = date(2026, 5, 10)
    ts = [
        datetime(2026, 5, 10, 1), datetime(2026, 5, 10, 23),
        datetime(2026, 5, 8, 12),
        datetime(2026, 4, 1), None,
    ]
    out = au.clicks_per_day(ts, 3, today=today)
    assert out == [
        {"date": "2026-05-08", "clicks": 1},
        {"date": "2026-05-09", "clicks": 0},
        {"date": "2026-05-10", "clicks": 2},
    ]


def test_top_counts_orders_and_defaults():
    out = au.top_counts(["a", "b", "b", None, None, None], limit=2)
    assert out == [{"name": "Unknown", "clicks": 3}, {"name": "b", "clicks": 2}]


def test_referrer_host():
    assert au.referrer_host("https://news.example.com/post?id=1") == "news.example.com"
    assert au.referrer_host("Direct") == "Direct"
    assert au.referrer_host(None) == "Direct"


def test_week_over_week():
    now = datetime(2026, 5, 15, tzinfo=timezone.utc)
    ts = [datetime(2026, 5, 14), datetime(2026, 5, 10), datetime(2026, 5, 5), datetime(2026, 4, 30)]
    assert au.week_over_week(ts, now=now) == {"last_7_days": 2, "previous_7_days": 1}
