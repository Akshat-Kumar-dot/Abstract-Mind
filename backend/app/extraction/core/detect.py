"""File type by magic bytes, and a quick paper-or-UPI check."""
from __future__ import annotations

import io
import re
import zipfile
from typing import Optional

from .models import Document

UPI_APPS = re.compile(r"phonepe|google\s*pay|g\s?pay|paytm|bhim|amazon\s*pay|cred\b|mobikwik|navi\b|whatsapp\s*pay", re.I)
VPA = re.compile(r"[A-Za-z0-9.\-_]{2,256}@[A-Za-z]{2,64}\b(?!\.)")


def sniff(data: bytes, filename: str = "") -> Optional[str]:
    head = data[:16]
    name = filename.lower()
    if head.startswith(b"%PDF") or b"%PDF" in data[:1024]:
        return "pdf"
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff") or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        return "image"
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if "word/document.xml" in z.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            return None
        return None
    if name.endswith(".tex") or b"\\documentclass" in data[:20000] or b"\\begin{document}" in data:
        return "tex"
    return None


def guess_kind(doc: Document) -> str:
    text = " ".join(b.text for b in doc.blocks[:400])
    upi = 0
    if re.search(r"(?<!\d)\d{12}(?!\d)", text):
        upi += 2
    if VPA.search(text):
        upi += 2
    if re.search(r"₹|\brs\.?\s?\d|\binr\b", text, re.I):
        upi += 1
    if UPI_APPS.search(text):
        upi += 2
    if re.search(r"\bupi\b", text, re.I):
        upi += 1
    paper = 0
    if re.search(r"\babstract\b|a\s?b\s?s\s?t\s?r\s?a\s?c\s?t", text, re.I):
        paper += 2
    if re.search(r"\breferences\b|\bbibliography\b", " ".join(b.text for b in doc.blocks), re.I):
        paper += 2
    if re.search(r"\bintroduction\b", text, re.I):
        paper += 1
    if (doc.pages or 1) >= 2:
        paper += 1
    if doc.source in ("docx", "tex"):
        paper += 2
    if paper == upi:
        return "paper" if (doc.pages or 1) > 1 else "upi"
    return "paper" if paper > upi else "upi"
