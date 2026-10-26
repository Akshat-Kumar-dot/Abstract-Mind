"""Heading patterns that hold in every template: Abstract, Keywords,
Introduction, References and the declaration sections."""
from __future__ import annotations

import re
from typing import Optional

from ..core.models import Block

NUM_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.):]?|[IVXLC]+[.)]|[A-Z][.)])\s+(?=\S)")

ANCHORS = {
    "abstract": re.compile(r"^(abstract|summary)\b", re.I),
    "keywords": re.compile(r"^(keywords?|key\s*words|index\s*terms)\b", re.I),
    "introduction": re.compile(r"^introduction\b", re.I),
    "references": re.compile(r"^(references|bibliography|literature\s+cited|works\s+cited|reference\s+list)\s*:?$", re.I),
    "acknowledgments": re.compile(r"^acknowledge?ments?\b", re.I),
    "appendix": re.compile(r"^(appendix|appendices|supplementary\s+(material|information))\b", re.I),
    "article_info": re.compile(r"^article\s+info(rmation)?\b", re.I),
    "biography": re.compile(r"^(biograph(y|ies)|author\s+biograph(y|ies)|about\s+the\s+authors?)\b", re.I),
}

# These may run straight into the text: "Abstract—We ...", "Keywords: a, b".
INLINE_OK = {"abstract", "keywords", "acknowledgments"}


def letters_unspaced(t: str) -> str:
    """Elsevier prints 'a b s t r a c t'; turn it back into 'abstract'."""
    if re.fullmatch(r"(?:[A-Za-z] ){3,}[A-Za-z]", t.strip()):
        return t.replace(" ", "")
    return t


def clean_heading(text: str) -> tuple[str, bool]:
    t = letters_unspaced(text.strip())
    numbered = bool(NUM_PREFIX.match(t)) and not ANCHORS["abstract"].match(t)
    t = NUM_PREFIX.sub("", t) if numbered else t
    return t.strip(), numbered


def heading_like(b: Block, body_size: float) -> bool:
    words = len(b.text.split())
    if words == 0 or words > 10:
        return False
    if b.style and (b.style == "heading" or b.style.lower().startswith("heading") or b.style.lower() == "title"):
        return True
    _, numbered = clean_heading(b.text)
    letters = re.sub(r"[^A-Za-z]", "", b.text)
    return b.bold or b.font_size >= body_size + 0.5 or numbered or (len(letters) > 3 and letters.isupper())


def anchor(b: Block, body_size: float) -> Optional[str]:
    t, _ = clean_heading(b.text)
    for kind, rx in ANCHORS.items():
        m = rx.match(t)
        if not m:
            continue
        rest = t[m.end():]
        if heading_like(b, body_size) and not rest.strip(" .:—–-"):
            return kind
        # Run-in heading: any punctuation after the word ("Abstract—", "Keywords:",
        # or a dash that extracted as an odd character).
        if kind in INLINE_OK and re.match(r"^\s*[^\w\s(]", rest):
            return kind
        # Bold "Abstract" followed straight by the text: "Abstract The paper ..."
        if kind == "abstract" and re.match(r"^\s+[A-Z]", rest) and (b.page or 1) <= 2:
            return kind
        if kind in ("abstract", "keywords") and not rest.strip():
            return kind
        if kind == "introduction" and heading_like(b, body_size) and len(t.split()) <= 4:
            return kind
    return None


def after_anchor(text: str) -> str:
    """'Abstract—This paper...' -> 'This paper...'."""
    t = letters_unspaced(text.strip())
    t = NUM_PREFIX.sub("", t)
    for kind in ("abstract", "keywords", "acknowledgments"):
        m = ANCHORS[kind].match(t)
        if m:
            rest = t[m.end():]
            return re.sub(r"^\s*[^\w\s(]+", "", rest).strip()
    return t
