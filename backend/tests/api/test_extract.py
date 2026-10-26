"""Uploads: raw body, hard limits, nothing stored, nothing sent anywhere,
hostile files refused quickly."""
import io
import socket
import struct
import time
import zlib

import fitz

from app.db import database
from app.extraction.service import run

from .helpers import API, client, signup


def upload(api, data: bytes, name: str = "file.pdf", **params):
    return api.post(f"{API}/extract", content=data, params=params, headers={"X-File-Name": name})


def test_extracts_a_paper_and_a_receipt(fixtures):
    api = client()
    paper = upload(api, (fixtures / "lncs.pdf").read_bytes(), "lncs.pdf")
    assert paper.status_code == 200 and paper.json()["kind"] == "paper"
    receipt = upload(api, (fixtures / "paytm.pdf").read_bytes(), "paytm.pdf")
    assert receipt.json()["kind"] == "upi"
    warned = upload(api, (fixtures / "paytm.pdf").read_bytes(), "paytm.pdf", kind="paper")
    assert "UPI receipt" in warned.json()["warnings"][0]


def test_extraction_is_never_stored_even_when_signed_in(fixtures):
    api = client()
    signup(api)
    r = upload(api, (fixtures / "lncs.pdf").read_bytes(), "lncs.pdf")
    assert r.status_code == 200 and "saved_id" not in r.json()
    with database.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_rejects_empty_unknown_and_oversized(monkeypatch):
    api = client()
    assert upload(api, b"").status_code == 400
    assert upload(api, b"hello there", "a.txt").status_code == 415
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.001")
    assert upload(api, b"%PDF" + b"x" * 5000).status_code == 413


def test_filename_is_sanitised(fixtures):
    api = client()
    r = upload(api, (fixtures / "paytm.pdf").read_bytes(), "..%2F..%2Fetc%2Fpass%3Cb%3Ewd%00.pdf")
    assert r.json()["filename"] == "passbwd.pdf"


def test_extraction_never_touches_the_network(fixtures, monkeypatch):
    """No file content can leave the machine: every outgoing connection and
    DNS lookup fails the test, then every kind of file is read (PDF, Word,
    LaTeX, screenshots through OCR, receipts)."""
    def blocked(*a, **k):
        raise AssertionError(f"extraction tried to use the network: {a[:2]}")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    for f in sorted(fixtures.iterdir()):
        if f.suffix.lower() in (".pdf", ".docx", ".tex", ".png", ".jpg", ".jpeg", ".webp"):
            result = run(f.read_bytes(), f.name)
            assert result["kind"] in ("paper", "upi"), f.name


def test_password_protected_pdf_is_refused():
    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "secret")
    data = pdf.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    r = upload(client(), data)
    assert r.status_code == 415 and "password" in r.json()["detail"]


def test_page_cap(fixtures, monkeypatch):
    monkeypatch.setenv("MAX_PDF_PAGES", "1")
    r = upload(client(), (fixtures / "ieee.pdf").read_bytes(), "ieee.pdf")
    assert r.status_code == 415 and "limit is 1" in r.json()["detail"]


def test_image_bomb_is_refused_before_decoding():
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", 20000, 20000, 8, 2, 0, 0, 0)     # claims 400 megapixels
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00")) + chunk(b"IEND", b"")
    r = upload(client(), png, "huge.png")
    assert r.status_code == 415 and "too large" in r.json()["detail"]


def test_word_zip_bomb_is_refused(fixtures, monkeypatch):
    from app.extraction.ingest import docx as docx_loader
    monkeypatch.setattr(docx_loader, "MAX_UNPACKED", 1000)
    r = upload(client(), (fixtures / "manuscript.docx").read_bytes(), "m.docx")
    assert r.status_code == 415 and "too large once unpacked" in r.json()["detail"]


def test_latex_size_cap_and_hostile_latex(monkeypatch):
    hostile = ("\\documentclass{article}\\begin{document}" + "\\begin{figure}x" * 20000).encode()
    started = time.monotonic()
    r = upload(client(), hostile, "evil.tex")
    assert r.status_code == 200 and time.monotonic() - started < 10       # linear, not stuck
    monkeypatch.setenv("MAX_TEX_KB", "1")
    assert upload(client(), hostile, "evil.tex").status_code == 415


def test_damaged_files_get_a_plain_error():
    assert upload(client(), b"%PDF-1.7\n garbage garbage").status_code in (415, 422)
    assert upload(client(), b"PK\x03\x04garbage", "x.docx").status_code == 415
