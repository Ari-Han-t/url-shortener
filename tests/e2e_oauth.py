"""End-to-end OAuth check against a RUNNING hop server (real Postgres and Redis).

    HOP_E2E_URL=http://127.0.0.1:8001 python tests/e2e_oauth.py          # prints a step-by-step report
    HOP_E2E_URL=... HOP_E2E_SLOW=1 python tests/e2e_oauth.py             # also waits 62 s to check code expiry

It creates one throwaway user. Under pytest it is skipped unless HOP_E2E_URL is set.
"""
import base64
import hashlib
import os
import re
import secrets
import sys
import time
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

BASE = os.getenv("HOP_E2E_URL", "").rstrip("/")
REDIRECT = "http://localhost:53682/callback"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

try:  # collected by pytest as a single skipped test when no server is configured
    import pytest

    @pytest.mark.skipif(not BASE, reason="set HOP_E2E_URL to run against a live server")
    def test_oauth_end_to_end():
        main()
except ImportError:  # pragma: no cover
    pass


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail and not ok else ''}")
    if not ok:
        raise AssertionError(label)


def pkce():
    v = secrets.token_urlsafe(48)
    return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")


def main() -> None:
    assert BASE, "set HOP_E2E_URL"
    web = httpx.Client(base_url=BASE, follow_redirects=False, timeout=20)  # the "browser" (keeps cookies)
    api = httpx.Client(base_url=BASE, follow_redirects=False, timeout=20)

    user, pw = "oa_" + secrets.token_hex(4), "pw-" + secrets.token_hex(8)
    check("register test user", api.post("/register", json={"username": user, "password": pw}).status_code == 200)
    jwt = api.post("/token", data={"username": user, "password": pw}).json()["access_token"]
    jwt_h = {"Authorization": f"Bearer {jwt}"}

    # 1. discovery
    r = api.post("/mcp", json=LIST, headers=MCP_HEADERS)
    www = r.headers.get("www-authenticate", "")
    m = re.search(r'resource_metadata="([^"]+)"', www)
    check("401 from /mcp carries resource_metadata", r.status_code == 401 and bool(m), www)
    prm = httpx.get(m.group(1)).json()
    resource = prm["resource"]
    check("protected resource metadata", resource.endswith("/mcp") and prm["authorization_servers"], str(prm))
    issuer = prm["authorization_servers"][0]
    p = urlparse(issuer)
    meta = httpx.get(f"{p.scheme}://{p.netloc}/.well-known/oauth-authorization-server{p.path}").json()
    meta_root = httpx.get(f"{p.scheme}://{p.netloc}/.well-known/oauth-authorization-server").json()
    check("AS metadata (path form and root form)", meta["issuer"] == issuer == meta_root["issuer"]
          and meta["code_challenge_methods_supported"] == ["S256"], str(meta))
    check("hop's own /register and /token untouched", api.post("/register", json={}).status_code == 422
          and api.post("/token", data={}).status_code == 422)

    # 2. dynamic client registration
    reg = httpx.post(meta["registration_endpoint"], json={
        "redirect_uris": [REDIRECT], "client_name": "E2E client", "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]})
    check("DCR (public client)", reg.status_code == 201, reg.text)
    cid = reg.json()["client_id"]
    bad = httpx.post(meta["registration_endpoint"], json={"redirect_uris": ["http://evil.example/cb"], "client_name": "x"})
    check("DCR rejects non-loopback http redirect", bad.status_code == 400 and bad.json()["error"] == "invalid_redirect_uri", bad.text)

    def authorize_url(challenge, **over):
        q = {"client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "code_challenge": challenge,
             "code_challenge_method": "S256", "state": "xyz", "resource": resource, **over}
        return meta["authorization_endpoint"] + "?" + urlencode({k: v for k, v in q.items() if v is not None})

    def run_browser_flow(challenge, decision="allow"):
        r = web.get(authorize_url(challenge))
        assert r.status_code == 302, (r.status_code, r.text)
        loc = r.headers["location"]
        page = web.get(loc if loc.startswith("http") else BASE + loc)
        req = parse_qs(urlparse(loc).query)["req"][0]
        if "Sign in to hop" in page.text:
            csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
            wrong = web.post("/oauth/consent/login", data={"req": req, "csrf": csrf, "username": user, "password": "nope"})
            check("wrong password is refused", wrong.status_code == 401)
            nocsrf = web.post("/oauth/consent/login", data={"req": req, "csrf": "bad", "username": user, "password": pw})
            check("login without valid CSRF is refused", nocsrf.status_code == 403)
            ok = web.post("/oauth/consent/login", data={"req": req, "csrf": csrf, "username": user, "password": pw})
            assert ok.status_code == 303, ok.text
            page = web.get(loc if loc.startswith("http") else BASE + loc)
        check("consent page names the client and permissions", "E2E client" in page.text and "read your links" in page.text)
        csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
        done = web.post("/oauth/consent", data={"req": req, "csrf": csrf, "decision": decision})
        assert done.status_code == 303, done.text
        return done.headers["location"]

    # 3. negative authorize cases
    _, ch = pkce()
    r = web.get(authorize_url(ch, redirect_uri="https://evil.example/cb"))
    check("unregistered redirect_uri is rejected, not redirected", r.status_code == 400 and "location" not in r.headers)
    r = web.get(authorize_url(ch, resource=BASE + "/not-mcp"))
    check("wrong resource is rejected", r.status_code == 400)
    r = web.get(authorize_url(ch, code_challenge_method="plain"))
    check("PKCE plain is rejected", "consent" not in r.headers.get("location", ""))
    r = web.get(authorize_url(None))
    check("missing code_challenge is rejected", "consent" not in r.headers.get("location", ""))

    # 4. happy path
    verifier, challenge = pkce()
    cb = run_browser_flow(challenge)
    q = parse_qs(urlparse(cb).query)
    check("callback has code and untouched state", cb.startswith(REDIRECT) and q["state"] == ["xyz"] and "code" in q)
    code = q["code"][0]

    def token_req(**f):
        return httpx.post(meta["token_endpoint"], data={"client_id": cid, **f})

    r = token_req(grant_type="authorization_code", code=code, redirect_uri=REDIRECT, code_verifier=secrets.token_urlsafe(48))
    check("wrong code_verifier fails", r.status_code == 400 and r.json()["error"] == "invalid_grant", r.text)
    r = token_req(grant_type="authorization_code", code=code, redirect_uri=REDIRECT, code_verifier=verifier)
    check("code is single use (consumed by the failed attempt)", r.status_code == 400, r.text)

    verifier, challenge = pkce()
    code = parse_qs(urlparse(run_browser_flow(challenge)).query)["code"][0]
    r = token_req(grant_type="authorization_code", code=code, redirect_uri="http://localhost:1/other", code_verifier=verifier)
    check("redirect_uri mismatch at /token fails", r.status_code == 400, r.text)

    verifier, challenge = pkce()
    code = parse_qs(urlparse(run_browser_flow(challenge)).query)["code"][0]
    r = token_req(grant_type="authorization_code", code=code, redirect_uri=REDIRECT, code_verifier=verifier)
    check("code + correct verifier gives tokens", r.status_code == 200, r.text)
    tok = r.json()
    check("token shape", tok["access_token"].startswith("hopat_") and tok["refresh_token"].startswith("hoprt_") and tok["expires_in"] == 3600)
    r = token_req(grant_type="authorization_code", code=code, redirect_uri=REDIRECT, code_verifier=verifier)
    check("reused code fails", r.status_code == 400, r.text)

    # 5. use the access token on /mcp
    h = {**MCP_HEADERS, "Authorization": f"Bearer {tok['access_token']}"}
    r = api.post("/mcp", json=LIST, headers=h)
    check("tools/list with OAuth access token", r.status_code == 200 and "list_links" in r.text, r.text[:200])
    sid = api.post("/shorten", json={"long_url": "https://example.com/oauth"}, headers=jwt_h).json()["data"]["Short_ID"]
    r = api.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_links", "arguments": {}}})
    check("tool call sees the signed-in user's link", sid in r.text, r.text[:200])
    apps = api.get("/connected-apps", headers=jwt_h).json()["data"]
    check("connected apps lists the client", any(a["client_id"] == cid and a["client_name"] == "E2E client" for a in apps), str(apps))

    # 6. refresh rotation
    r = token_req(grant_type="refresh_token", refresh_token=tok["refresh_token"])
    check("refresh gives new tokens", r.status_code == 200, r.text)
    new = r.json()
    check("refresh token rotated", new["refresh_token"] != tok["refresh_token"])
    r = token_req(grant_type="refresh_token", refresh_token=tok["refresh_token"])
    check("old refresh token rejected", r.status_code == 400 and r.json()["error"] == "invalid_grant", r.text)
    check("old access token rejected", api.post("/mcp", json=LIST, headers=h).status_code == 401)
    h2 = {**MCP_HEADERS, "Authorization": f"Bearer {new['access_token']}"}
    check("reuse of a rotated refresh token also revoked the new pair", api.post("/mcp", json=LIST, headers=h2).status_code == 401)

    # 7. revocation
    verifier, challenge = pkce()
    code = parse_qs(urlparse(run_browser_flow(challenge)).query)["code"][0]
    tok = token_req(grant_type="authorization_code", code=code, redirect_uri=REDIRECT, code_verifier=verifier).json()
    h3 = {**MCP_HEADERS, "Authorization": f"Bearer {tok['access_token']}"}
    check("fresh token works", api.post("/mcp", json=LIST, headers=h3).status_code == 200)
    r = httpx.post(meta["revocation_endpoint"], data={"token": tok["refresh_token"], "client_id": cid})
    check("revocation endpoint answers 200", r.status_code == 200, r.text)
    check("access denied after revoke", api.post("/mcp", json=LIST, headers=h3).status_code == 401)

    # 8. deny, and revoking from hop's UI endpoint
    cb = run_browser_flow(pkce()[1], decision="deny")
    check("deny redirects with access_denied and state", "error=access_denied" in cb and "state=xyz" in cb and "code=" not in cb)
    verifier, challenge = pkce()
    code = parse_qs(urlparse(run_browser_flow(challenge)).query)["code"][0]
    tok = token_req(grant_type="authorization_code", code=code, redirect_uri=REDIRECT, code_verifier=verifier).json()
    h4 = {**MCP_HEADERS, "Authorization": f"Bearer {tok['access_token']}"}
    r = api.post(f"/connected-apps/{cid}/revoke", headers=jwt_h)
    check("Disconnect from hop revokes the grant", r.status_code == 200 and api.post("/mcp", json=LIST, headers=h4).status_code == 401, r.text)

    # 9. API keys still work
    key = api.post("/api-keys", json={"name": "e2e"}, headers=jwt_h).json()["data"]["key"]
    r = api.post("/mcp", json=LIST, headers={**MCP_HEADERS, "Authorization": f"Bearer {key}"})
    check("API key still opens /mcp", r.status_code == 200 and "list_links" in r.text, r.text[:200])
    check("bogus token is 401 with invalid_token", 'error="invalid_token"' in api.post(
        "/mcp", json=LIST, headers={**MCP_HEADERS, "Authorization": "Bearer hopat_bogus"}).headers.get("www-authenticate", ""))

    # 10. optional: authorization code expiry (60 s)
    if os.getenv("HOP_E2E_SLOW"):
        verifier, challenge = pkce()
        code = parse_qs(urlparse(run_browser_flow(challenge)).query)["code"][0]
        time.sleep(62)
        r = token_req(grant_type="authorization_code", code=code, redirect_uri=REDIRECT, code_verifier=verifier)
        check("code expires after 60 seconds", r.status_code == 400 and "expired" in r.text, r.text)

    print("\nAll OAuth end-to-end checks passed.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("FAILED:", e)
        sys.exit(1)
