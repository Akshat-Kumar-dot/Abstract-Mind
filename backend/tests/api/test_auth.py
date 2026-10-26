"""Accounts and sessions under the zero-knowledge protocol."""
import os

from app.db import database

from .helpers import API, b64, client, credentials, document, signup


def test_signup_returns_key_material_and_a_safe_cookie():
    api = client()
    creds = credentials()
    r = api.post(f"{API}/auth/signup", json={"email": "Ada@Example.org", "name": "Ada", **creds})
    assert r.status_code == 200
    body = r.json()
    assert body["user"] == {"name": "Ada", "email": "ada@example.org", "guest": False, "since": body["user"]["since"],
                            "needs_password": False}
    assert body["key"]["wrapped_key"] == creds["wrapped_key"] and body["key"]["salt"] == creds["kdf_salt"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie


def test_server_never_stores_the_auth_key():
    api = client()
    creds = signup(api)
    with database.connect() as con:
        row = con.execute("SELECT * FROM users").fetchone()
    stored = b"".join(v if isinstance(v, bytes) else str(v).encode() for v in row)
    assert creds["auth_key"].encode() not in stored
    assert row["auth_hash"] != creds["auth_key"]


def test_prelogin_does_not_reveal_whether_an_account_exists():
    api = client()
    creds = signup(api)
    known = api.post(f"{API}/auth/prelogin", json={"email": "ada@example.org"}).json()
    assert known["salt"] == creds["kdf_salt"]
    a = api.post(f"{API}/auth/prelogin", json={"email": "nobody@example.org"}).json()
    b = api.post(f"{API}/auth/prelogin", json={"email": "nobody@example.org"}).json()
    assert a == b and set(a) == set(known) and a["iterations"] == 600_000


def test_login_logout_and_uniform_errors():
    api = client()
    creds = signup(api)
    api.post(f"{API}/auth/logout")
    assert api.get(f"{API}/auth/me").status_code == 401
    wrong = api.post(f"{API}/auth/login", json={"email": "ada@example.org", "auth_key": b64(os.urandom(32))})
    unknown = api.post(f"{API}/auth/login", json={"email": "who@example.org", "auth_key": b64(os.urandom(32))})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    ok = api.post(f"{API}/auth/login", json={"email": "ADA@example.org", "auth_key": creds["auth_key"]})
    assert ok.status_code == 200 and ok.json()["key"]["wrapped_key"] == creds["wrapped_key"]
    assert api.get(f"{API}/auth/me").json()["user"]["email"] == "ada@example.org"


def test_logging_in_replaces_the_old_session():
    api = client()
    creds = signup(api)
    old = api.cookies.get("am_session")
    api.post(f"{API}/auth/login", json={"email": "ada@example.org", "auth_key": creds["auth_key"]})
    stale = client()
    stale.cookies.set("am_session", old)
    assert stale.get(f"{API}/auth/me").status_code == 401


def test_duplicate_and_malformed_signups():
    api = client()
    signup(api)
    again = api.post(f"{API}/auth/signup", json={"email": "ada@example.org", **credentials()})
    assert again.status_code == 400
    bad = credentials()
    bad["auth_key"] = b64(os.urandom(16))          # wrong length
    r = api.post(f"{API}/auth/signup", json={"email": "x@example.org", **bad})
    assert r.status_code == 422 and bad["auth_key"] not in r.text
    weak = credentials()
    weak["kdf_iterations"] = 1000                  # too few PBKDF2 rounds
    assert api.post(f"{API}/auth/signup", json={"email": "y@example.org", **weak}).status_code == 422
    assert api.post(f"{API}/auth/signup", json={"email": "not-an-email", **credentials()}).status_code == 422
    extra = {"email": "z@example.org", "is_admin": True, **credentials()}
    assert api.post(f"{API}/auth/signup", json=extra).status_code == 422


def test_login_attempts_are_rate_limited():
    api = client()
    signup(api)
    codes = [api.post(f"{API}/auth/login", json={"email": "ada@example.org", "auth_key": b64(os.urandom(32))}).status_code
             for _ in range(9)]
    assert codes[:8] == [401] * 8 and codes[8] == 429


def test_guest_claim_keeps_documents():
    api = client()
    r = api.post(f"{API}/auth/guest")
    assert r.status_code == 200 and r.json()["user"]["guest"] is True and r.json()["key"] is None
    assert api.post(f"{API}/documents", json=document()).status_code == 201
    creds = credentials()
    claimed = api.post(f"{API}/auth/claim", json={"email": "g@example.org", "name": "Grace", **creds})
    assert claimed.status_code == 200 and claimed.json()["key"]["wrapped_key"] == creds["wrapped_key"]
    assert api.post(f"{API}/auth/claim", json={"email": "h@example.org", **credentials()}).status_code == 400
    api.post(f"{API}/auth/logout")
    again = client()
    assert again.post(f"{API}/auth/login", json={"email": "g@example.org", "auth_key": creds["auth_key"]}).status_code == 200
    assert again.get(f"{API}/documents").json()["stats"]["total"] == 1


def test_guest_logout_deletes_the_guest_and_its_documents():
    api = client()
    api.post(f"{API}/auth/guest")
    api.post(f"{API}/documents", json=document())
    api.post(f"{API}/auth/logout")
    with database.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_change_password_rewraps_and_signs_out_other_sessions():
    api = client()
    creds = signup(api)
    other = client()
    other.post(f"{API}/auth/login", json={"email": "ada@example.org", "auth_key": creds["auth_key"]})
    new = credentials()
    wrong = api.post(f"{API}/account/password", json={"current_auth_key": b64(os.urandom(32)), **new})
    assert wrong.status_code == 401
    ok = api.post(f"{API}/account/password", json={"current_auth_key": creds["auth_key"], **new})
    assert ok.status_code == 200 and ok.json()["key"]["wrapped_key"] == new["wrapped_key"]
    assert other.get(f"{API}/auth/me").status_code == 401          # signed out elsewhere
    assert api.get(f"{API}/auth/me").status_code == 200            # still in here
    fresh = client()
    assert fresh.post(f"{API}/auth/login", json={"email": "ada@example.org", "auth_key": creds["auth_key"]}).status_code == 401
    assert fresh.post(f"{API}/auth/login", json={"email": "ada@example.org", "auth_key": new["auth_key"]}).status_code == 200


def test_delete_account_needs_the_password_and_removes_everything():
    api = client()
    creds = signup(api)
    api.post(f"{API}/documents", json=document())
    assert api.post(f"{API}/account/delete", json={"auth_key": creds["auth_key"], "confirm": "yes"}).status_code == 422
    assert api.post(f"{API}/account/delete", json={"auth_key": b64(os.urandom(32)), "confirm": "delete my account"}).status_code == 401
    assert api.post(f"{API}/account/delete", json={"auth_key": creds["auth_key"], "confirm": "delete my account"}).status_code == 200
    assert api.get(f"{API}/auth/me").status_code == 401
    with database.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
