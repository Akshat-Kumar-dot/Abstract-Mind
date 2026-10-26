"""Affiliation helpers: does a line look like an affiliation, and splitting one
into department, institution, city and country."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from ..core.text import EMAIL_RE, MARKER_RE, ascii_fold, collapse
from ..data import load_list

# Long words also match as prefixes (Universität, Institutional); short ones only whole.
_words = load_list("affiliation_words.txt")
AFF_WORDS = re.compile(
    r"\b(?:" + "|".join(re.escape(w) + (r"\w*" if len(w) >= 6 else "") for w in _words) + r")\b", re.I)
DEPT = re.compile(r"\b(dept\.?|department|school\s+of|faculty\s+of|division\s+of|college\s+of|centre\s+for|center\s+for|laboratory\s+(?:for|of)|lab\s+(?:for|of)|group|unit)\b", re.I)
INST = re.compile(r"\b(universit\w*|institut\w*|college|école|ecole|academy|polytechnic|politecnico|hospital|laborator\w*|centre|center|inc\b|ltd|llc|gmbh|corporation|corp\b|research|iit\b|nit\b|iiit\b|bits\b|iisc\b|iiser\b|cnrs|inria|csir|drdo|isro)", re.I)


@lru_cache(maxsize=1)
def countries() -> frozenset:
    import pycountry

    names = set()
    for c in pycountry.countries:
        for attr in ("name", "official_name", "common_name"):
            v = getattr(c, attr, None)
            if v:
                names.add(_key(v))
    names.update(_key(a) for a in load_list("country_aliases.txt"))
    return frozenset(names)


def _key(s: str) -> str:
    return collapse(re.sub(r"[^a-z ]", " ", ascii_fold(s).lower()))


def country_of(part: str) -> Optional[str]:
    """The country named in `part`, as written, if any."""
    cleaned = collapse(re.sub(r"\d", " ", part)).strip(" .,;")
    if _key(cleaned) in countries():
        return cleaned
    words = cleaned.split()
    for n in (3, 2, 1):   # "Bangalore 560012 India" -> "India"
        if len(words) > n and _key(" ".join(words[-n:])) in countries():
            return " ".join(words[-n:])
    return None


def ends_with_country(line: str) -> bool:
    parts = [p for p in re.split(r"[,;]", strip_noise(line)) if p.strip()]
    return bool(parts) and country_of(parts[-1]) is not None


def looks_like_affiliation(line: str) -> bool:
    t = strip_noise(line)
    return bool(AFF_WORDS.search(t)) or ends_with_country(t)


def strip_noise(text: str) -> str:
    text = MARKER_RE.sub(" ", text)
    text = re.sub(r"\(?\s*e-?mail\s*:?[^)]*\)?", " ", text, flags=re.I)
    text = EMAIL_RE.sub(" ", text)
    return collapse(text).strip(" ,;.")


def parse(text: str) -> dict:
    t = strip_noise(text)
    parts = [p.strip() for p in re.split(r"[,;]", t) if p.strip()]
    out = {"department": None, "institution": None, "city": None, "country": None}
    if not parts:
        return out
    ci = None
    for i in range(len(parts) - 1, -1, -1):
        c = country_of(parts[i])
        if c:
            out["country"], ci = c, i
            break
    states = set(load_list("indian_states.txt"))
    if ci is not None:
        j = ci - 1
        tail = parts[ci][: -len(out["country"])].strip() if parts[ci] != out["country"] else ""
        candidates = ([tail] if tail else []) + [parts[k] for k in range(j, max(j - 3, -1), -1)]
        for cand in candidates:
            cand = collapse(re.sub(r"\b[\w-]*\d[\w-]*\b", " ", cand)).strip(" -")
            if not cand or (len(cand) <= 2 and cand.isupper()) or cand.lower() in states:
                continue
            if INST.search(cand) or DEPT.search(cand):
                break
            out["city"] = cand
            break
    for p in parts:
        if out["department"] is None and DEPT.search(p) and not re.match(r"^\s*(universit|institut)", p, re.I):
            out["department"] = p
        elif out["institution"] is None and INST.search(p):
            out["institution"] = p
    inst_parts = [p for p in parts if INST.search(p) and p != out["department"]]
    if out["department"] is None and len(inst_parts) >= 2:
        # "Institute of Informatics, TU Munich": the unit comes first, then the institution
        out["department"], out["institution"] = inst_parts[0], inst_parts[1]
    if out["institution"] is None:
        rest = [p for p in parts if p not in (out["department"], out["city"]) and country_of(p) is None]
        if rest:
            out["institution"] = max(rest, key=len)
    return out
