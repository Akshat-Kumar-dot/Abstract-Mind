"""Saved documents, stored as ciphertext.

The browser encrypts every document with the account's data key before sending
it; this module only ever handles opaque base64 strings. Titles, kinds and
counts are inside the encrypted `meta`, so even the library list is readable
only in the owner's browser.
"""
from __future__ import annotations

import secrets
import time
from typing import Optional

from .database import connect

WEEK = 7 * 86400


def new_id() -> str:
    return secrets.token_urlsafe(12)       # 16 characters, 96 random bits


def count(user_id: int) -> int:
    with connect() as con:
        return con.execute("SELECT COUNT(*) FROM documents WHERE user_id = ?", (user_id,)).fetchone()[0]


def create(user_id: int, meta: str, body: str) -> dict:
    doc_id, now = new_id(), time.time()
    with connect() as con:
        con.execute("INSERT INTO documents (id, user_id, meta, body, size, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (doc_id, user_id, meta, body, len(meta) + len(body), now, now))
    return {"id": doc_id, "created_at": now, "updated_at": now}


def _summary(row) -> dict:
    return {"id": row["id"], "meta": row["meta"], "starred": bool(row["starred"]), "size": row["size"],
            "created_at": row["created_at"], "updated_at": row["updated_at"]}


def list_for(user_id: int) -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT id, meta, starred, size, created_at, updated_at FROM documents "
                           "WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
    return [_summary(r) for r in rows]


def get(user_id: int, doc_id: str) -> Optional[dict]:
    with connect() as con:
        row = con.execute("SELECT * FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id)).fetchone()
    return {**_summary(row), "body": row["body"]} if row else None


def update(user_id: int, doc_id: str, meta: str, body: str) -> bool:
    with connect() as con:
        cur = con.execute("UPDATE documents SET meta = ?, body = ?, size = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                          (meta, body, len(meta) + len(body), time.time(), doc_id, user_id))
        return cur.rowcount > 0


def set_starred(user_id: int, doc_id: str, starred: bool) -> bool:
    with connect() as con:
        cur = con.execute("UPDATE documents SET starred = ? WHERE id = ? AND user_id = ?", (int(starred), doc_id, user_id))
        return cur.rowcount > 0


def delete(user_id: int, doc_id: str) -> bool:
    with connect() as con:
        return con.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id)).rowcount > 0


def stats(user_id: int) -> dict:
    """What the server can count without reading anything: documents per week."""
    now = time.time()
    with connect() as con:
        rows = con.execute("SELECT created_at FROM documents WHERE user_id = ?", (user_id,)).fetchall()
    weeks = [0] * 12
    for r in rows:
        ago = int((now - r["created_at"]) // WEEK)
        if 0 <= ago < 12:
            weeks[11 - ago] += 1
    return {"total": len(rows), "this_week": weeks[-1], "weeks": weeks}
