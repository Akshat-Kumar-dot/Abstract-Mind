"""Stand-ins for what the browser does. The server treats the auth key, salt,
wrapped key and documents as opaque bytes, so random values are enough here;
the real key derivation is tested in tests/web (Node)."""
import base64
import os

from fastapi.testclient import TestClient

from app.main import app

API = "/api/v1"


def client() -> TestClient:
    return TestClient(app)


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def credentials() -> dict:
    return {"auth_key": b64(os.urandom(32)), "kdf_salt": b64(os.urandom(16)), "kdf_iterations": 600_000,
            "wrapped_key": b64(b"\x01" + os.urandom(60))}


def signup(api: TestClient, email: str = "ada@example.org", name: str = "Ada") -> dict:
    creds = credentials()
    r = api.post(f"{API}/auth/signup", json={"email": email, "name": name, **creds})
    assert r.status_code == 200, r.text
    return creds


def ciphertext(n: int = 120) -> str:
    """Shaped like the browser's envelope: version byte, IV, ciphertext."""
    return b64(b"\x01" + os.urandom(n))


def document() -> dict:
    return {"meta": ciphertext(80), "body": ciphertext(600)}
