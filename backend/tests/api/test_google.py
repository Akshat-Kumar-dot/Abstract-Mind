"""Continue with Google. Google's token endpoint is replaced by a stand-in that
returns the claims a real ID token would carry."""
import time
from urllib.parse import parse_qs, urlparse

import pytest

from app.api.routes import google
from app.db import database

from .helpers import API, client, credentials, document

CLIENT_ID = "test-client.apps.googleusercontent.com"


@pytest.fixture(autouse=True)
def google_on(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")


def sign_in_with_google(api, monkeypatch, sub="g-123", email="ada@example.org", name="Ada Lovelace", **overrides):
    start = api.get(f"{API}/auth/google/start", follow_redirects=False)
    assert start.status_code == 303
    sent = parse_qs(urlparse(start.headers["location"]).query)
    assert sent["client_id"] == [CLIENT_ID] and sent["redirect_uri"][0].endswith("/api/v1/auth/google/callback")

    def fake_exchange(code, redirect_uri, s):
        assert code == "the-code"
        return {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "exp": time.time() + 300,
                "nonce": sent["nonce"][0], "sub": sub, "email": email, "email_verified": True, "name": name, **overrides}

    monkeypatch.setattr(google, "exchange_code", fake_exchange)
    return api.get(f"{API}/auth/google/callback", params={"code": "the-code", "state": sent["state"][0]},
                   follow_redirects=False)


def test_new_google_account_must_set_a_password_once(monkeypatch):
    api = client()
    r = sign_in_with_google(api, monkeypatch)
    assert r.status_code == 303 and r.headers["location"] == "/#/"
    me = api.get(f"{API}/auth/me").json()
    assert me["user"]["email"] == "ada@example.org" and me["user"]["needs_password"] is True and me["key"] is None

    creds = credentials()
    r = api.post(f"{API}/auth/password", json=creds)
    assert r.status_code == 200 and r.json()["key"]["wrapped_key"] == creds["wrapped_key"]
    assert r.json()["user"]["needs_password"] is False
    # never a second time: changing it needs the current password
    assert api.post(f"{API}/auth/password", json=credentials()).status_code == 400


def test_returning_google_user_gets_the_same_account_and_key(monkeypatch):
    first = client()
    sign_in_with_google(first, monkeypatch)
    creds = credentials()
    first.post(f"{API}/auth/password", json=creds)
    first.post(f"{API}/documents", json=document())

    other_device = client()
    sign_in_with_google(other_device, monkeypatch)
    me = other_device.get(f"{API}/auth/me").json()
    assert me["key"]["wrapped_key"] == creds["wrapped_key"] and me["stats"]["total"] == 1
    with database.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_guest_who_continues_with_google_keeps_their_documents(monkeypatch):
    api = client()
    api.post(f"{API}/auth/guest")
    api.post(f"{API}/documents", json=document())
    sign_in_with_google(api, monkeypatch)
    me = api.get(f"{API}/auth/me").json()
    assert me["user"]["guest"] is False and me["user"]["needs_password"] is True and me["stats"]["total"] == 1


def test_existing_email_account_is_linked_not_duplicated(monkeypatch):
    api = client()
    creds = credentials()
    api.post(f"{API}/auth/signup", json={"email": "ada@example.org", "name": "Ada", **creds})
    api.post(f"{API}/auth/logout")
    sign_in_with_google(api, monkeypatch)
    me = api.get(f"{API}/auth/me").json()
    assert me["user"]["needs_password"] is False and me["key"]["wrapped_key"] == creds["wrapped_key"]


@pytest.mark.parametrize("bad, reason", [
    ({"aud": "someone-else"}, "failed"),
    ({"iss": "https://evil.example"}, "failed"),
    ({"exp": 1}, "failed"),
    ({"nonce": "replayed"}, "failed"),
    ({"email_verified": False}, "unverified"),
])
def test_bad_id_tokens_are_refused(monkeypatch, bad, reason):
    api = client()
    r = sign_in_with_google(api, monkeypatch, **bad)
    assert r.status_code == 303 and r.headers["location"] == f"/?signin={reason}#/signup"
    assert api.get(f"{API}/auth/me").status_code == 401


def test_callback_without_the_state_cookie_is_refused(monkeypatch):
    api = client()
    monkeypatch.setattr(google, "exchange_code", lambda *a: pytest.fail("must not call Google"))
    r = api.get(f"{API}/auth/google/callback", params={"code": "x", "state": "guessed"}, follow_redirects=False)
    assert r.headers["location"] == "/?signin=expired#/signup"


def test_google_is_off_without_credentials(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET")
    api = client()
    assert api.get(f"{API}/health").json()["google"] is False
    r = api.get(f"{API}/auth/google/start", follow_redirects=False)
    assert r.headers["location"] == "/?signin=off#/signup"


def test_set_password_is_only_for_google_accounts_without_one():
    api = client()
    assert api.post(f"{API}/auth/password", json=credentials()).status_code == 401
    api.post(f"{API}/auth/guest")
    assert api.post(f"{API}/auth/password", json=credentials()).status_code == 400
