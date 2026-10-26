"""Small text helpers shared by both pipelines."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
# {alice, bob}@uni.edu and (alice,bob)@uni.edu
GROUP_EMAIL_RE = re.compile(r"[{(]\s*([A-Za-z0-9._%+\-]+(?:\s*[,;|]\s*[A-Za-z0-9._%+\-]+)+)\s*[})]\s*@\s*([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)")
ORCID_RE = re.compile(r"\b(\d{4}-\d{4}-\d{4}-\d{3}[\dX])\b")
MARKER_RE = re.compile(r"\^\{([^}]*)\}")
SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
UNICODE_SUP_RE = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
WORD_RE = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def ascii_fold(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def strip_markers(s: str) -> str:
    return collapse(MARKER_RE.sub("", s))


def unicode_sup_to_marked(s: str) -> str:
    return UNICODE_SUP_RE.sub(lambda m: "^{" + m.group(0).translate(SUPERSCRIPT_DIGITS) + "}", s)


def join_lines(lines: Iterable[str]) -> str:
    """Join text lines, undoing end-of-line hyphenation ("lan-" + "guage")."""
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out.endswith("-") and line[:1].islower() and len(out) > 1 and out[-2].isalpha():
            out = out[:-1] + line
        elif out:
            out += " " + line
        else:
            out = line
    return out


def normalize(s: str) -> str:
    """Form used for grounding checks: folded, lower case, punctuation dropped."""
    s = ascii_fold(nfkc(s)).lower()
    s = re.sub(r"-\s+", "", s)
    s = re.sub(r"[^a-z0-9@.\s]", " ", s)
    return collapse(s)


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def find_emails(text: str) -> list[str]:
    found: list[str] = []
    for m in GROUP_EMAIL_RE.finditer(text):
        for local in re.split(r"\s*[,;|]\s*", m.group(1)):
            if local:
                found.append(f"{local}@{m.group(2)}")
    stripped = GROUP_EMAIL_RE.sub(" ", text)
    for m in EMAIL_RE.finditer(stripped):
        found.append(m.group(0).rstrip("."))
    seen, out = set(), []
    for e in found:
        k = e.lower()
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out
