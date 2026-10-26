"""Other websites (READER_ALLOWED_ORIGINS, e.g. the TrustNet form on Cloudflare)
may use the reader from the browser: /extract and /health only, no cookies,
and nothing is ever stored."""
import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.main import create_app

from .helpers import API, client

FORM = "https://trustnet-form.pages.dev"
OTHER = "https://evil.example"


@pytest.fixture(autouse=True)
def form_allowed(monkeypatch):
    monkeypatch.setenv("READER_ALLOWED_ORIGINS", f"{FORM}, https://second.example/")


def extract_from(api, origin, fixtures, name="lncs.pdf"):
    return api.post(f"{API}/extract", content=(fixtures / name).read_bytes(), params={"kind": "paper"},
                    headers={"Origin": origin, "X-File-Name": name, "Content-Type": "application/octet-stream"})


def counts():
    with database.connect() as con:
        return [con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("users", "sessions", "documents")]


def test_the_form_can_read_a_paper_and_nothing_is_stored(fixtures):
    api = client()
    pre = api.options(f"{API}/extract", headers={"Origin": FORM, "Access-Control-Request-Method": "POST",
                                                 "Access-Control-Request-Headers": "content-type, x-file-name"})
    assert pre.status_code == 204
    assert pre.headers["access-control-allow-origin"] == FORM
    assert "x-file-name" in pre.headers["access-control-allow-headers"].lower()

    before = counts()
    r = extract_from(api, FORM, fixtures)
    assert r.status_code == 200 and r.json()["kind"] == "paper"
    assert r.headers["access-control-allow-origin"] == FORM
    assert "access-control-allow-credentials" not in r.headers          # never as a signed-in user
    assert counts() == before == [0, 0, 0]


def test_a_trailing_slash_in_the_setting_is_fine(fixtures):
    r = extract_from(client(), "https://second.example", fixtures)
    assert r.status_code == 200


def test_health_can_be_checked_to_wake_the_server():
    r = client().get(f"{API}/health", headers={"Origin": FORM})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == FORM


def test_other_websites_are_refused(fixtures):
    api = client()
    pre = api.options(f"{API}/extract", headers={"Origin": OTHER, "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in pre.headers
    r = extract_from(api, OTHER, fixtures)
    assert r.status_code == 403 and "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize("method, path", [
    ("post", "/auth/guest"), ("post", "/auth/login"), ("get", "/auth/me"),
    ("get", "/documents"), ("post", "/documents"), ("post", "/auth/logout"),
])
def test_the_form_gets_nothing_but_the_reader(method, path):
    api = client()
    r = getattr(api, method)(f"{API}{path}", headers={"Origin": FORM})
    assert "access-control-allow-origin" not in r.headers
    if method == "post":
        assert r.status_code == 403
    pre = api.options(f"{API}{path}", headers={"Origin": FORM, "Access-Control-Request-Method": method.upper()})
    assert "access-control-allow-origin" not in pre.headers
    assert counts() == [0, 0, 0]


def test_localhost_is_allowed_only_in_development(monkeypatch, fixtures):
    local = "http://localhost:8790"
    assert extract_from(client(), local, fixtures).status_code == 200
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET", "x" * 32)
    prod = TestClient(create_app(), base_url="https://testserver")
    r = extract_from(prod, local, fixtures)
    assert r.status_code == 403 and "access-control-allow-origin" not in r.headers
    assert extract_from(prod, FORM, fixtures).status_code == 200
