"""Sessions: a random token in an HttpOnly cookie; only its SHA-256 is stored,
so a copy of the database can't be used to take over a session."""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Optional

from .database import connect
from .users import User, _row_to_user


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(user_id: int, days: int) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with connect() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        # Guests that no longer have any session can never be reached again.
        con.execute("DELETE FROM users WHERE is_guest = 1 AND id != ? AND id NOT IN (SELECT user_id FROM sessions)", (user_id,))
        con.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (_digest(token), user_id, now, now + days * 86400))
    return token


def resolve(token: Optional[str]) -> Optional[User]:
    if not token or len(token) > 128:
        return None
    with connect() as con:
        row = con.execute("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                          "WHERE s.token_hash = ? AND s.expires_at > ?", (_digest(token), time.time())).fetchone()
    return _row_to_user(row) if row else None


def revoke(token: str) -> None:
    """Ends one session. Ending a guest's session deletes the guest: nothing
    could ever log back in to it."""
    with connect() as con:
        row = con.execute("SELECT u.id, u.is_guest FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
                          (_digest(token),)).fetchone()
        con.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(token),))
        if row and row["is_guest"]:
            con.execute("DELETE FROM users WHERE id = ?", (row["id"],))


def revoke_others(user_id: int, keep_token: Optional[str]) -> None:
    with connect() as con:
        con.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user_id, _digest(keep_token or "")))
