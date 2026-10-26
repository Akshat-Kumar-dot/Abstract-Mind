"""Evidence score for each author candidate. Candidates only ever come from the
header zone; this catches leftovers such as editor lines."""
from __future__ import annotations

import re

from .header import Author, Header

THRESHOLD = 2


def score(a: Author, h: Header) -> int:
    s = 0
    if a.affiliations:
        s += 2
    if a.email:
        s += 2
    if h.title_blocks and not a.line.in_footnote:
        s += 1
    if a.link_mode == "layout":
        s += 1
    t = a.line.block.text
    if re.search(r"\bet\s+al\b", t, re.I):
        s -= 3
    if re.search(r"\b(19|20)\d{2}\b|\[\d+\]", t):
        s -= 3
    if re.search(r"received|accepted|editor|communicated\s+by|reviewer", t, re.I):
        s -= 2
    return s


def apply(h: Header) -> None:
    for a in h.authors:
        a.score = score(a, h)
