"""Declaration sections: funding, conflicts, data availability, author
contributions, ethics. Found by heading, or by a run-in label like 'Funding:'."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..core.models import Block
from ..core.text import join_lines
from ..data import load_list
from .anchors import clean_heading, heading_like

KINDS = {
    "funding": re.compile(r"^(funding(\s+information|\s+statement)?|financial\s+support|grant\s+information|sources?\s+of\s+funding)\b", re.I),
    "conflicts": re.compile(r"^(conflicts?\s+of\s+interests?|competing\s+interests?|declaration\s+of\s+competing\s+interests?|disclosure\s+statement|declarations?\s+of\s+interests?)\b", re.I),
    "data": re.compile(r"^(data\s+(and\s+code\s+)?availability(\s+statement)?|code\s+availability|data\s+access(\s+statement)?)\b", re.I),
    "contributions": re.compile(r"^(author\s+contributions?(\s+statement)?|credit\s+authorship\s+contribution\s+statement|contributions)\b", re.I),
    "ethics": re.compile(r"^(ethics(\s+approval|\s+statement|\s+declarations?)?|ethical\s+(approval|statement|considerations)|informed\s+consent(\s+statement)?|institutional\s+review\s+board\s+statement)\b", re.I),
    "acknowledgments": re.compile(r"^acknowledge?ments?\b", re.I),
}
GRANT = re.compile(
    r"(?:grants?|awards?|projects?|contracts?|agreements?|fund(?:ing)?)\s*(?:no\.?|nos\.?|numbers?|#|ids?|code)?\s*[:.]?\s*"
    r"((?:[A-Z0-9][A-Za-z0-9/.\-]{2,}[A-Za-z0-9])(?:\s*(?:,|and|&)\s*(?:[A-Z0-9][A-Za-z0-9/.\-]{2,}[A-Za-z0-9]))*)",
    re.I,
)
APPROVAL = re.compile(r"(?:approval|protocol|irb|reference|ref\.?)\s*(?:no\.?|number|#|code)?\s*[:.]?\s*([A-Z0-9][A-Za-z0-9/.\-]{3,})", re.I)
URL = re.compile(r"https?://\S+|\bdoi\.org/\S+|\bgithub\.com/\S+|\bzenodo\.org/\S+")


@dataclass
class Section:
    kind: str
    text: str
    block: Block


@dataclass
class Declarations:
    sections: dict[str, Section] = field(default_factory=dict)
    grant_ids: list[str] = field(default_factory=list)
    funding_text: Optional[str] = None
    funding_block: Optional[Block] = None
    credit_roles: list[str] = field(default_factory=list)
    data_urls: list[str] = field(default_factory=list)
    approval_ids: list[str] = field(default_factory=list)


def _kind(b: Block, body_size: float) -> tuple[Optional[str], str]:
    t, _ = clean_heading(b.text)
    for kind, rx in KINDS.items():
        m = rx.match(t)
        if not m:
            continue
        rest = t[m.end():]
        if heading_like(b, body_size) and not rest.strip(" .:—–-"):
            return kind, ""
        if re.match(r"^\s*[^\w\s(]", rest):
            return kind, rest.lstrip(" :.—–").strip()
        # Bold run-in heading with no punctuation: "**Acknowledgements** We thank ..."
        if b.lead_bold and rx.match(clean_heading(b.lead_bold)[0]):
            return kind, rest.strip()
        # Same without bold information, only for unmistakable headings
        if re.match(r"^\s+[A-Z]", rest) and (kind in ("acknowledgments", "funding") or len(m.group(0).split()) >= 2):
            return kind, rest.strip()
    return None, ""


def find(blocks: list[Block], body_size: float) -> Declarations:
    d = Declarations()
    i = 0
    while i < len(blocks):
        kind, inline = _kind(blocks[i], body_size)
        if not kind or kind in d.sections:
            i += 1
            continue
        lines = [inline] if inline else []
        j = i + 1
        while j < len(blocks):
            b = blocks[j]
            k2, _ = _kind(b, body_size)
            if k2 or (heading_like(b, body_size) and len(b.text.split()) <= 8 and not b.text.rstrip().endswith(".")):
                break
            lines.append(b.text)
            j += 1
            if len(" ".join(lines)) > 2000:
                break
        text = join_lines(lines)
        if text:
            d.sections[kind] = Section(kind, text, blocks[i])
        i = j

    if "funding" in d.sections:
        d.funding_text, d.funding_block = d.sections["funding"].text, d.sections["funding"].block
    elif "acknowledgments" in d.sections:
        ack = d.sections["acknowledgments"]
        sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z][a-z])", ack.text) if re.search(r"fund|grant|support(ed)?\s+by|financ|sponsor", s, re.I)]
        if sentences:
            d.funding_text, d.funding_block = " ".join(sentences), ack.block
    if d.funding_text:
        for m in GRANT.finditer(d.funding_text):
            for gid in re.split(r"\s*(?:,|and|&)\s*", m.group(1)):
                gid = gid.strip(" .")
                if re.search(r"\d", gid) and len(gid) >= 4 and gid not in d.grant_ids:
                    d.grant_ids.append(gid)
    if "contributions" in d.sections:
        text = d.sections["contributions"].text.lower().replace("-", "–")
        for role in load_list("credit_roles.txt"):
            key = role.lower()
            if key in text or key.replace(" – ", " ") in text.replace(" – ", " "):
                d.credit_roles.append(role)
    if "data" in d.sections:
        d.data_urls = [u.rstrip(".,;)") for u in URL.findall(d.sections["data"].text)]
    if "ethics" in d.sections:
        d.approval_ids = [m.group(1).rstrip(".,;") for m in APPROVAL.finditer(d.sections["ethics"].text) if re.search(r"\d", m.group(1))]
    return d
