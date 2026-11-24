"""Checks the /mcp mount, auth and tool wiring with the database mocked out."""
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import main
import mcp_server

HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def rpc(method, params=None, id_=1):
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}


def test_reserved_aliases_cover_new_routes():
    assert {"mcp", "api-keys"} <= main.RESERVED_ALIASES


def test_mcp_requires_key(client):
    conn = mock.MagicMock()
    conn.cursor.return_value.fetchone.return_value = None  # no matching key row
    with mock.patch.object(mcp_server.db_pool, "getconn", return_value=conn):
        _check_unauthorised(client)


def _check_unauthorised(client):
    r = client.post("/mcp", json=rpc("tools/list"), headers=HEADERS)
    assert r.status_code == 401
    r = client.post("/mcp", json=rpc("tools/list"), headers={**HEADERS, "Authorization": "Bearer hop_nope_nope_nope_nope_nope"})
    assert r.status_code == 401


def test_mcp_lists_tools_and_runs_one_as_the_key_owner(client):
    principal = mcp_server.Principal(user_id=7, key_id=3)
    cursor = mock.MagicMock()
    cursor.fetchall.return_value = [("abc", "https://example.com", 4, None, None, None)]
    conn = mock.MagicMock()
    conn.cursor.return_value = cursor
    h = {**HEADERS, "Authorization": "Bearer hop_" + "x" * 40}

    with mock.patch.object(mcp_server, "resolve_principal", return_value=principal), \
         mock.patch.object(mcp_server, "_rate_limited", return_value=False), \
         mock.patch.object(mcp_server.db_pool, "getconn", return_value=conn):
        r = client.post("/mcp", json=rpc("tools/list"), headers=h)
        assert r.status_code == 200, r.text
        names = {t["name"] for t in r.json()["result"]["tools"]}
        assert names == {"list_links", "link_analytics", "recent_clicks", "account_summary", "create_short_link", "update_link", "clicks_by"}

        r = client.post("/mcp", json=rpc("tools/call", {"name": "list_links", "arguments": {}}), headers=h)
        assert r.status_code == 200, r.text
        assert "https://hop.test/abc" in r.text
        # The query was scoped to the key owner.
        assert cursor.execute.call_args[0][1] == (7,)


def test_mcp_rate_limit(client):
    h = {**HEADERS, "Authorization": "Bearer hop_" + "x" * 40}
    with mock.patch.object(mcp_server, "resolve_principal", return_value=mcp_server.Principal(1, 1)), \
         mock.patch.object(mcp_server, "_rate_limited", return_value=True):
        assert client.post("/mcp", json=rpc("tools/list"), headers=h).status_code == 429
