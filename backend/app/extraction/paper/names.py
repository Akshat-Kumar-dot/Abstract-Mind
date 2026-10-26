"""Name helpers: is this token part of a person's name, and how to split it."""
from __future__ import annotations

import re

from ..data import load_list

PARTICLES = set(load_list("name_particles.txt"))
NOT_NAMES = {"the", "of", "for", "in", "on", "with", "a", "an", "to", "from", "by", "at", "is", "are", "we", "this", "our",
             "abstract", "introduction", "keywords", "email", "e-mail", "corresponding", "author", "authors", "university",
             "department", "institute", "received", "accepted", "editor", "member", "fellow", "ieee", "student", "senior"}


def is_name_token(t: str) -> bool:
    t = t.strip(",;")
    if not t:
        return False
    if t.lower() in PARTICLES:
        return True
    if t.lower().strip(".") in NOT_NAMES:
        return False
    if re.fullmatch(r"(?:[A-Z]\.-?){1,3}", t):     # A.  A.K.  J.-P.
        return True
    if not t[0].isupper():
        return False
    return all(ch.isalpha() or ch in ".'’-" for ch in t)


def is_name(part: str) -> bool:
    tokens = part.split()
    if not 2 <= len(tokens) <= 5:
        return False
    if not all(is_name_token(t) for t in tokens):
        return False
    return any(len(t.strip(".")) >= 2 and t.lower() not in PARTICLES for t in tokens)


def split_name(name: str) -> tuple[str, str]:
    """Return (first, last). Keeps initials with the first name and particles
    with the last name; 'Last, First' and 'John SMITH' are recognised."""
    name = " ".join(name.split())
    if "," in name:
        last, first = [p.strip() for p in name.split(",", 1)]
        return first, last
    tokens = name.split()
    if len(tokens) == 1:
        return "", tokens[0]
    caps = [i for i, t in enumerate(tokens) if len(t) > 2 and t.isupper() and "." not in t]
    if caps and len(caps) < len(tokens):
        last = " ".join(tokens[i] for i in caps)
        first = " ".join(t for i, t in enumerate(tokens) if i not in caps)
        return first, last
    i = len(tokens) - 2
    last = tokens[-1]
    while i >= 1 and tokens[i].lower() in PARTICLES:
        last = tokens[i] + " " + last
        i -= 1
    return " ".join(tokens[: i + 1]), last
