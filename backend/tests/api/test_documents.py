"""The encrypted library: the server stores what the browser sent, checks sizes,
quotas and ownership, and can't read any of it."""
import re

from app.db import database

from .helpers import API, b64, ciphertext, client, document, signup


def test_requires_sign_in():
    api = client()
    assert api.get(f"{API}/documents").status_code == 401
    assert api.post(f"{API}/documents", json=document()).status_code == 401


def test_create_list_read_replace_star_delete():
    api = client()
    signup(api)
    doc = document()
    created = api.post(f"{API}/documents", json=doc)
    assert created.status_code == 201
    doc_id = created.json()["id"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{16}", doc_id)

    listed = api.get(f"{API}/documents").json()
    assert [d["id"] for d in listed["documents"]] == [doc_id]
    assert listed["documents"][0]["meta"] == doc["meta"] and "body" not in listed["documents"][0]
    assert listed["stats"]["total"] == 1 and listed["stats"]["weeks"][-1] == 1

    got = api.get(f"{API}/documents/{doc_id}").json()
    assert got["meta"] == doc["meta"] and got["body"] == doc["body"]

    new = document()
    assert api.put(f"{API}/documents/{doc_id}", json=new).status_code == 200
    assert api.get(f"{API}/documents/{doc_id}").json()["body"] == new["body"]
    assert api.patch(f"{API}/documents/{doc_id}", json={"starred": True}).status_code == 200
    assert api.get(f"{API}/documents").json()["documents"][0]["starred"] is True
    assert api.delete(f"{API}/documents/{doc_id}").status_code == 200
    assert api.get(f"{API}/documents/{doc_id}").status_code == 404


def test_other_users_cannot_see_or_touch_a_document():
    owner = client()
    signup(owner)
    doc_id = owner.post(f"{API}/documents", json=document()).json()["id"]
    intruder = client()
    signup(intruder, "eve@example.org", "Eve")
    assert intruder.get(f"{API}/documents/{doc_id}").status_code == 404
    assert intruder.put(f"{API}/documents/{doc_id}", json=document()).status_code == 404
    assert intruder.patch(f"{API}/documents/{doc_id}", json={"starred": True}).status_code == 404
    assert intruder.delete(f"{API}/documents/{doc_id}").status_code == 404
    assert intruder.get(f"{API}/documents").json()["documents"] == []
    assert owner.get(f"{API}/documents/{doc_id}").status_code == 200


def test_rejects_malformed_ids_and_bodies():
    api = client()
    signup(api)
    assert api.get(f"{API}/documents/../../etc").status_code in (404, 422)
    assert api.get(f"{API}/documents/short").status_code == 422
    assert api.post(f"{API}/documents", json={"meta": "not base64 !!!" * 5, "body": ciphertext()}).status_code == 422
    assert api.post(f"{API}/documents", json={"meta": ciphertext(), "body": ciphertext(), "user_id": 1}).status_code == 422


def test_quota_and_size_limits(monkeypatch):
    monkeypatch.setenv("MAX_DOCUMENTS_PER_USER", "2")
    monkeypatch.setenv("MAX_DOCUMENT_KB", "2")
    api = client()
    signup(api)
    assert api.post(f"{API}/documents", json=document()).status_code == 201
    assert api.post(f"{API}/documents", json=document()).status_code == 201
    assert api.post(f"{API}/documents", json=document()).status_code == 409
    big = {"meta": ciphertext(80), "body": ciphertext(4000)}
    assert api.post(f"{API}/documents", json=big).status_code == 413


def test_database_holds_only_ciphertext():
    api = client()
    signup(api)
    doc = document()
    api.post(f"{API}/documents", json=doc)
    with database.connect() as con:
        row = con.execute("SELECT meta, body FROM documents").fetchone()
    assert (row["meta"], row["body"]) == (doc["meta"], doc["body"])     # stored exactly as sent, never decoded
