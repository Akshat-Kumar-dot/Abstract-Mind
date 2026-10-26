"""Cross-cutting protections: headers, cross-site requests, body limits,
production cookie settings, no API schema exposure, no input echo."""
import pytest

from app.settings import get_settings

from .helpers import API, b64, client, credentials


def test_security_headers_on_pages_and_api():
    api = client()
    page = api.get("/")
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    for r in (page, api.get(f"{API}/health")):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "no-referrer"
    assert api.get(f"{API}/health").headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in page.headers          # only in production


def test_cross_site_writes_are_blocked():
    api = client()
    body = {"email": "a@example.org", **credentials()}
    evil = api.post(f"{API}/auth/signup", json=body, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    sneaky = api.post(f"{API}/auth/guest", headers={"Sec-Fetch-Site": "cross-site"})
    assert sneaky.status_code == 403
    same = api.post(f"{API}/auth/signup", json=body, headers={"Origin": "http://testserver"})
    assert same.status_code == 200
    ext = api.post(f"{API}/auth/logout", headers={"Origin": "chrome-extension://abcdefghijklmnop"})
    assert ext.status_code == 200


def test_oversized_json_is_refused():
    r = client().post(f"{API}/auth/login", content=b"{" + b" " * 100_000 + b"}", headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_no_schema_or_docs_exposed():
    api = client()
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert api.get(path).status_code == 404


def test_static_files_cannot_escape_the_web_folder():
    api = client()
    for path in ("/../backend/app/settings.py", "/%2e%2e/backend/app/settings.py", "/..%2f.env", "/practice/../../data/abstract_mind.db"):
        r = api.get(path)
        assert r.status_code == 404 or b"APP_SECRET" not in r.content


def test_validation_errors_do_not_echo_input():
    secret = b64(b"x" * 20)
    r = client().post(f"{API}/auth/login", json={"email": "a@example.org", "auth_key": secret})
    assert r.status_code == 422 and secret not in r.text and r.json()["fields"] == ["auth_key"]


def test_production_requires_a_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        get_settings()


def test_production_cookie_is_secure_and_host_only(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET", "s" * 40)
    api = client()
    r = api.post(f"{API}/auth/guest")
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("__Host-am_session=") and "Secure" in cookie and "Domain" not in cookie
    assert "max-age=31536000" in r.headers["strict-transport-security"]

