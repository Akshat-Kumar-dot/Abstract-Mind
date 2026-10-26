"""Grounding: a value is only trusted if it can be found in the text it came from."""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from .text import normalize


def grounded(value: str, haystack_normalized: str, threshold: int = 90) -> bool:
    v = normalize(value)
    if not v:
        return False
    if v in haystack_normalized:
        return True
    if len(v) < 4:
        return False
    return fuzz.partial_ratio(v, haystack_normalized) >= threshold


def orcid_ok(orcid: str) -> bool:
    """ISO 7064 MOD 11-2 checksum used by ORCID iDs."""
    digits = orcid.replace("-", "").upper()
    if not re.fullmatch(r"\d{15}[\dX]", digits):
        return False
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    r = (12 - total % 11) % 11
    return digits[-1] == ("X" if r == 10 else str(r))


def email_ok(email: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}", email))
