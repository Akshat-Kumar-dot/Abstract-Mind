"""Hashing of the auth key the browser sends at sign-up and log-in.

The browser never sends the password itself. It stretches the password with
PBKDF2-SHA256 (600,000 rounds) and sends one half of the result, the auth key.
The server stores only a scrypt hash of that key, so a stolen database doesn't
let anyone log in, and the other half (the wrapping key) never reaches the
server at all.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_DUMMY_SALT = b"\x00" * 16


def new_salt() -> bytes:
    return secrets.token_bytes(16)


def hash_auth_key(auth_key: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(auth_key, salt=salt, n=2**14, r=8, p=1, dklen=32)


def verify(auth_key: bytes, salt: bytes, expected: bytes) -> bool:
    return hmac.compare_digest(hash_auth_key(auth_key, salt), expected)


def burn_time(auth_key: bytes) -> None:
    """Do the same work as a real check, so an unknown email takes as long as a
    wrong password and response times don't reveal which emails exist."""
    hash_auth_key(auth_key, _DUMMY_SALT)


def fake_kdf_salt(email: str, secret: bytes) -> bytes:
    """A stable salt for emails that have no account, so the pre-login step
    looks the same whether or not an account exists."""
    return hmac.new(secret, b"kdf-salt:" + email.encode(), hashlib.sha256).digest()[:16]
