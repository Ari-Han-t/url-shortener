import hashlib

import pytest

import oauth

RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"  # RFC 7636 appendix B


def test_pkce_rfc_vector_and_failures():
    assert oauth.verify_pkce(RFC_VERIFIER, RFC_CHALLENGE)
    assert not oauth.verify_pkce(RFC_VERIFIER[::-1], RFC_CHALLENGE)
    assert not oauth.verify_pkce(RFC_VERIFIER, RFC_VERIFIER)  # "plain" does not pass as S256
    assert not oauth.verify_pkce("short", RFC_CHALLENGE)  # verifier must be 43-128 chars
    assert not oauth.verify_pkce("a" * 129, RFC_CHALLENGE)
    assert not oauth.verify_pkce(RFC_VERIFIER[:-1] + "!", RFC_CHALLENGE)


@pytest.mark.parametrize("uri,ok", [
    ("https://claude.ai/api/mcp/auth_callback", True),
    ("https://example.com/cb?x=1", True),
    ("http://localhost:3118/callback", True),
    ("http://127.0.0.1:54321/cb", True),
    ("http://[::1]:8080/cb", True),
    ("http://example.com/cb", False),
    ("http://localhost.evil.com/cb", False),
    ("http://127.0.0.1.evil.com/cb", False),
    ("javascript:alert(1)", False),
    ("data:text/html,x", False),
    ("com.example.app:/cb", False),
    ("https://example.com/cb#frag", False),
    ("https://user:pw@example.com/cb", False),
    ("https:///nohost", False),
    ("", False),
])
def test_redirect_uri_validation(uri, ok):
    assert oauth.redirect_uri_allowed(uri) is ok


def test_token_hashing_and_format():
    t = oauth.new_token("hopat_")
    assert t.startswith("hopat_") and len(t) > 40
    assert oauth.hash_token(t) == hashlib.sha256(t.encode()).hexdigest()
    assert oauth.hash_token(t) != t and t not in oauth.hash_token(t)
    assert oauth.new_token("hopat_") != t


def test_expiry_helper():
    assert oauth.is_expired(100, now=100)
    assert oauth.is_expired(99, now=100)
    assert not oauth.is_expired(101, now=100)
    assert oauth.CODE_TTL == 60 and oauth.ACCESS_TTL == 3600 and oauth.REFRESH_TTL == 30 * 86400


def test_csrf_bound_expiring_and_tamper_proof():
    tok = oauth.make_csrf("req1", 7, now=1000, secret="s" * 40)
    assert oauth.check_csrf(tok, "req1", 7, now=1001, secret="s" * 40)
    assert not oauth.check_csrf(tok, "req2", 7, now=1001, secret="s" * 40)  # other request
    assert not oauth.check_csrf(tok, "req1", 8, now=1001, secret="s" * 40)  # other user
    assert not oauth.check_csrf(tok, "req1", 7, now=1001, secret="x" * 40)  # other secret
    assert not oauth.check_csrf(tok, "req1", 7, now=1000 + oauth.CSRF_TTL + 1, secret="s" * 40)
    exp, sig = tok.split(".")
    assert not oauth.check_csrf(f"{int(exp) + 5}.{sig}", "req1", 7, now=1001, secret="s" * 40)
    for bad in ("", "garbage", "1.2.3", "x.y"):
        assert not oauth.check_csrf(bad, "req1", 7, now=1001, secret="s" * 40)


def test_session_cookie_signing_and_expiry():
    v = oauth.make_session(5, now=1000, secret="k" * 40)
    assert oauth.read_session(v, now=1001, secret="k" * 40) == 5
    assert oauth.read_session(v, now=1000 + oauth.SESSION_TTL + 1, secret="k" * 40) is None
    assert oauth.read_session(v, now=1001, secret="z" * 40) is None
    assert oauth.read_session(v.replace("5:", "6:", 1), now=1001, secret="k" * 40) is None
    assert oauth.read_session(None) is None and oauth.read_session("junk") is None


def test_origin_and_resource_matching(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    assert oauth.public_origin({"host": "hop.example"}, "http") == "http://hop.example"
    assert oauth.public_origin({"Host": "hop.example", "X-Forwarded-Proto": "https"}, "http") == "https://hop.example"
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://short.example/")
    assert oauth.public_origin({"host": "internal:8000"}, "http") == "https://short.example"
    o = "https://short.example"
    assert oauth.resource_matches(None, o)
    assert oauth.resource_matches("https://short.example/mcp", o)
    assert oauth.resource_matches("https://short.example/mcp/", o)
    assert not oauth.resource_matches("https://short.example/other", o)
    assert not oauth.resource_matches("https://evil.example/mcp", o)


def test_metadata_documents():
    o = "https://short.example"
    as_meta = oauth.authorization_server_metadata(o)
    assert as_meta["issuer"] == "https://short.example/oauth"
    assert as_meta["authorization_endpoint"] == "https://short.example/oauth/authorize"
    assert as_meta["token_endpoint"] == "https://short.example/oauth/token"
    assert as_meta["registration_endpoint"] == "https://short.example/oauth/register"
    assert as_meta["code_challenge_methods_supported"] == ["S256"]
    assert "none" in as_meta["token_endpoint_auth_methods_supported"]
    prm = oauth.protected_resource_metadata(o)
    assert prm["resource"] == "https://short.example/mcp"
    assert prm["authorization_servers"] == ["https://short.example/oauth"]
    assert oauth.resource_metadata_url(o) == "https://short.example/.well-known/oauth-protected-resource/mcp"
