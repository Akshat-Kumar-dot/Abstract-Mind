"""Accounts.

The server never sees a password. The browser derives two keys from it: an
auth key, sent at sign-up and log-in and stored here only as a scrypt hash,
and a wrapping key that never leaves the browser. The wrapping key encrypts
the account's data key; `wrapped_key` is that encrypted data key. The server
keeps it so the person can log in on another device, but cannot open it.

Guest accounts have no email or credentials; their data key lives only in the
browser that created them until they set an email and password ("claim").

Google accounts are found by Google's account id. Google proves who the person
is but gives the app nothing secret, so a new Google account has no wrapped
key until the person sets a password (`needs_password`); that password then
protects the data key exactly as above.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Optional

from ..security import passwords
from .database import connect

KDF_ALGORITHM = "pbkdf2-sha256"
DEFAULT_ITERATIONS = 600_000


class AccountError(ValueError):
    pass


@dataclass(frozen=True)
class Credentials:
    auth_key: bytes           # 32 bytes
    kdf_salt: bytes           # 16–64 bytes
    kdf_iterations: int
    wrapped_key: str          # base64 envelope made in the browser


@dataclass(frozen=True)
class User:
    id: int
    email: Optional[str]
    name: str
    is_guest: bool
    created_at: float
    kdf_salt: Optional[bytes]
    kdf_iterations: Optional[int]
    wrapped_key: Optional[str]

    @property
    def needs_password(self) -> bool:
        return not self.is_guest and not self.wrapped_key

    def public(self) -> dict:
        return {"name": self.name, "email": self.email, "guest": self.is_guest, "since": self.created_at,
                "needs_password": self.needs_password}

    def key_material(self) -> Optional[dict]:
        """What the browser needs to unlock the data key with the password."""
        if self.is_guest or not self.wrapped_key:
            return None
        return {"kdf": KDF_ALGORITHM, "salt": base64.b64encode(self.kdf_salt).decode(),
                "iterations": self.kdf_iterations, "wrapped_key": self.wrapped_key}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _row_to_user(row) -> User:
    return User(id=row["id"], email=row["email"], name=row["name"], is_guest=bool(row["is_guest"]),
                created_at=row["created_at"], kdf_salt=row["kdf_salt"], kdf_iterations=row["kdf_iterations"],
                wrapped_key=row["wrapped_key"])


def get(user_id: int) -> Optional[User]:
    with connect() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def create(email: str, name: str, creds: Credentials) -> User:
    salt, now = passwords.new_salt(), time.time()
    with connect() as con:
        if con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise AccountError("An account with this email already exists. Log in instead.")
        user_id = con.insert(
            "INSERT INTO users (email, name, is_guest, auth_hash, auth_salt, kdf_salt, kdf_iterations, wrapped_key, "
            "created_at, updated_at) VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?)",
            (email, name, passwords.hash_auth_key(creds.auth_key, salt), salt, creds.kdf_salt, creds.kdf_iterations,
             creds.wrapped_key, now, now))
    return get(user_id)


def create_guest() -> User:
    now = time.time()
    with connect() as con:
        user_id = con.insert("INSERT INTO users (name, is_guest, created_at, updated_at) VALUES ('Guest', 1, ?, ?)", (now, now))
    return get(user_id)


def claim(user_id: int, email: str, name: str, creds: Credentials) -> User:
    """Turn a guest into a full account, keeping its documents."""
    salt = passwords.new_salt()
    with connect() as con:
        if con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise AccountError("An account with this email already exists.")
        cur = con.execute(
            "UPDATE users SET email = ?, name = ?, is_guest = 0, auth_hash = ?, auth_salt = ?, kdf_salt = ?, "
            "kdf_iterations = ?, wrapped_key = ?, updated_at = ? WHERE id = ? AND is_guest = 1",
            (email, name, passwords.hash_auth_key(creds.auth_key, salt), salt, creds.kdf_salt, creds.kdf_iterations,
             creds.wrapped_key, time.time(), user_id))
        if not cur.rowcount:
            raise AccountError("This account already has an email and password.")
    return get(user_id)


def from_google(sub: str, email: str, name: str, guest_id: Optional[int] = None) -> User:
    """The account for a Google sign-in. Matched by Google id first, then by a
    verified email already registered here (the account is linked). Otherwise
    the signed-in guest, if any, becomes this account and keeps its documents;
    or a new account is made."""
    now = time.time()
    with connect() as con:
        row = con.execute("SELECT id FROM users WHERE google_sub = ?", (sub,)).fetchone()
        if row:
            return get(row["id"])
        row = con.execute("SELECT id FROM users WHERE email = ? AND is_guest = 0", (email,)).fetchone()
        if row:
            con.execute("UPDATE users SET google_sub = ?, updated_at = ? WHERE id = ?", (sub, now, row["id"]))
            user_id = row["id"]
        elif guest_id is not None and con.execute(
                "UPDATE users SET email = ?, name = ?, is_guest = 0, google_sub = ?, updated_at = ? WHERE id = ? AND is_guest = 1",
                (email, name, sub, now, guest_id)).rowcount:
            user_id = guest_id
        else:
            user_id = con.insert(
                "INSERT INTO users (email, name, is_guest, google_sub, created_at, updated_at) VALUES (?, ?, 0, ?, ?, ?)",
                (email, name, sub, now, now))
    return get(user_id)


def set_first_password(user_id: int, creds: Credentials) -> bool:
    """A Google account's first password. Never replaces one: that needs the
    current password (change_credentials)."""
    salt = passwords.new_salt()
    with connect() as con:
        cur = con.execute(
            "UPDATE users SET auth_hash = ?, auth_salt = ?, kdf_salt = ?, kdf_iterations = ?, wrapped_key = ?, updated_at = ? "
            "WHERE id = ? AND is_guest = 0 AND wrapped_key IS NULL",
            (passwords.hash_auth_key(creds.auth_key, salt), salt, creds.kdf_salt, creds.kdf_iterations, creds.wrapped_key,
             time.time(), user_id))
    return cur.rowcount > 0


def authenticate(email: str, auth_key: bytes) -> Optional[User]:
    with connect() as con:
        row = con.execute("SELECT * FROM users WHERE email = ? AND is_guest = 0", (email,)).fetchone()
    if row is None:
        passwords.burn_time(auth_key)
        return None
    if not passwords.verify(auth_key, row["auth_salt"], row["auth_hash"]):
        return None
    return _row_to_user(row)


def prelogin(email: str, secret: bytes) -> dict:
    """KDF parameters for an email. Unknown emails get a stable fake salt, so
    this step doesn't reveal whether an account exists."""
    with connect() as con:
        row = con.execute("SELECT kdf_salt, kdf_iterations FROM users WHERE email = ? AND is_guest = 0", (email,)).fetchone()
    salt = row["kdf_salt"] if row else passwords.fake_kdf_salt(email, secret)
    iterations = row["kdf_iterations"] if row else DEFAULT_ITERATIONS
    return {"kdf": KDF_ALGORITHM, "salt": base64.b64encode(salt).decode(), "iterations": iterations}


def change_credentials(user_id: int, current_auth_key: bytes, new: Credentials) -> bool:
    with connect() as con:
        row = con.execute("SELECT auth_hash, auth_salt FROM users WHERE id = ? AND is_guest = 0", (user_id,)).fetchone()
        if row is None or not passwords.verify(current_auth_key, row["auth_salt"], row["auth_hash"]):
            return False
        salt = passwords.new_salt()
        con.execute("UPDATE users SET auth_hash = ?, auth_salt = ?, kdf_salt = ?, kdf_iterations = ?, wrapped_key = ?, "
                    "updated_at = ? WHERE id = ?",
                    (passwords.hash_auth_key(new.auth_key, salt), salt, new.kdf_salt, new.kdf_iterations,
                     new.wrapped_key, time.time(), user_id))
    return True


def verify_auth_key(user_id: int, auth_key: bytes) -> bool:
    with connect() as con:
        row = con.execute("SELECT auth_hash, auth_salt FROM users WHERE id = ? AND is_guest = 0", (user_id,)).fetchone()
    return row is not None and passwords.verify(auth_key, row["auth_salt"], row["auth_hash"])


def delete(user_id: int) -> None:
    """Removes the account; sessions and documents go with it (ON DELETE CASCADE)."""
    with connect() as con:
        con.execute("DELETE FROM users WHERE id = ?", (user_id,))
