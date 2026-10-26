"""Header parsing: title, then every other header line is classified as author,
affiliation, email, note or noise. Only header lines can produce authors."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from ..core.models import Block
from ..core.text import collapse, find_emails, join_lines, strip_markers, unicode_sup_to_marked
from . import affiliations as aff
from .names import is_name
from .zones import Zones

SYMBOLS = "*†‡§¶✉∗⋆#☆"
NOISE = re.compile(
    r"(preprint|submitted\s+to|under\s+review|accepted\s+(?:for|at|in)|manuscript\s+received|received[:\s]|revised[:\s]|"
    r"arxiv:|journal\s+of|proceedings\s+of|transactions\s+on|\bvol\.|volume\s+\d|\bdoi\b|©|copyright|\bissn\b|licen[cs]e|"
    r"creative\s+commons|available\s+online|^\s*(research|original|review)\s+(article|paper)\s*$|conference\s+on|workshop\s+on)",
    re.I,
)
NOTE_CORR = re.compile(r"correspond|e-?mail\s+address|to\s+whom|^\s*✉", re.I)
NOTE_EQUAL = re.compile(r"contributed\s+equally|equal\s+contribution|joint\s+first|co-first", re.I)
STATEMENT = re.compile(r"\b(?:is|are)\s+(?:also\s+|currently\s+|now\s+)?with\s+(?:the\s+)?", re.I)
IEEE_MEMBER = re.compile(r",?\s*\b(?:Student\s+|Senior\s+|Life\s+|Graduate\s+Student\s+)?(?:Member|Fellow),?\s+IEEE\b", re.I)
BLIND = re.compile(r"\banonymous\b|author\(?s?\)?\s+(?:omitted|hidden|withheld)|blind(?:ed)?\s+(?:for\s+)?(?:review|submission)", re.I)


@dataclass
class Line:
    block: Block
    kind: str
    index: int
    emails: list[str] = field(default_factory=list)
    names: list[tuple[str, list[str], int]] = field(default_factory=list)   # (name, markers, char offset)
    aff_text: Optional[str] = None
    in_footnote: bool = False


@dataclass
class Author:
    name: str
    markers: list[str]
    line: Line
    offset: int = 0
    email: Optional[str] = None
    email_how: Optional[str] = None
    orcid: Optional[str] = None
    affiliations: list[str] = field(default_factory=list)
    affiliation_parts: list[dict] = field(default_factory=list)
    link_mode: Optional[str] = None
    corresponding: bool = False
    corresponding_how: Optional[str] = None
    equal: bool = False
    score: int = 0
    source: str = "rule"
    note: Optional[str] = None
    agreed: bool = False          # the LLM read the same name
    failed: int = 0               # checks this author failed


@dataclass
class AffEntry:
    markers: list[str]
    lines: list[Line]

    @property
    def text(self) -> str:
        return aff.strip_noise(join_lines(ln.aff_text or ln.block.text for ln in self.lines))


@dataclass
class Header:
    title: Optional[str] = None
    title_source: str = "rule"
    title_blocks: list[Block] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    authors: list[Author] = field(default_factory=list)
    affiliations: list[AffEntry] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    double_blind: bool = False


# ------------------------------------------------------------------ names

def prep_marked(marked: str) -> str:
    s = unicode_sup_to_marked(marked)
    s = IEEE_MEMBER.sub("", s)
    s = re.sub(r"\b\d+\^\{(?:st|nd|rd|th)\}\s*", "", s)                 # 1^{st} Name
    s = re.sub(r"(?<![\w^{])\d+(?:st|nd|rd|th)\s+(?=[A-Z])", "", s)      # 1st Name (IEEE template)
    # Markers that lost their superscript: "Smith1,2" -> "Smith^{1,2}"
    s = re.sub(r"(?<=[^\W\d_])(\d{1,2}(?:\s*,\s*\d{1,2})*)(?=\s*(?:,|;|\band\b|&|$|\s|[" + SYMBOLS + r"]))", r"^{\1}", s)
    return s


def split_names(marked: str) -> list[tuple[str, list[str], int]]:
    s = prep_marked(marked)
    s = re.sub(r"\^\{([^}]*)\}", lambda m: "^{" + m.group(1).replace(",", "|").replace(" ", "") + "}", s)
    raw_parts = re.split(r"\s*(?:,|;|\band\b|&|·|\s{3,})\s*", s)
    out: list[tuple[str, list[str], int]] = []
    plain = strip_markers(marked)
    for part in raw_parts:
        if not part.strip():
            continue
        markers: list[str] = []
        lead = re.match(r"^\s*\^\{([^}]*)\}", part)
        if lead and out and not out[-1][1]:
            # "Smith,^{1} Jones^{2}": the leading marker belongs to Smith
            out[-1] = (out[-1][0], [m for m in lead.group(1).split("|") if m], out[-1][2])
            part = part[lead.end():]
        for grp in re.findall(r"\^\{([^}]*)\}", part):
            markers += [m for m in grp.split("|") if m]
        name = re.sub(r"\^\{[^}]*\}", "", part)
        for sym in SYMBOLS:
            if sym in name:
                markers.append(sym)
                name = name.replace(sym, "")
        name = collapse(re.sub(r"\d+", "", name)).strip(" .,:")
        if not name:
            if markers and out:
                out[-1] = (out[-1][0], out[-1][1] + markers, out[-1][2])
            continue
        offset = plain.find(name.split()[0]) if name.split() else 0
        out.append((name, markers, max(offset, 0)))
    return out


def looks_like_names(marked: str) -> bool:
    plain = strip_markers(prep_marked(marked))
    if not plain or len(plain.split()) > 45 or plain.rstrip().endswith((".", ":")) and len(plain.split()) > 6:
        return False
    parts = split_names(marked)
    if not parts:
        return False
    good = sum(1 for n, _, _ in parts if is_name(n))
    return good >= max(1, math.ceil(0.7 * len(parts)))


# ------------------------------------------------------------------ lines

def classify(b: Block) -> tuple[str, list[str], Optional[str], list]:
    t = b.text
    emails = find_emails(t)
    no_mail = aff.strip_noise(t)
    if NOTE_CORR.search(t):
        return "corr_note", emails, None, []
    if NOTE_EQUAL.search(t):
        return "equal_note", emails, None, []
    if STATEMENT.search(t) and aff.looks_like_affiliation(t):
        return "statement", emails, None, []
    if NOISE.search(t) and not emails and not aff.AFF_WORDS.search(t):
        return "noise", emails, None, []
    if emails and len(re.sub(r"(?i)e-?mails?|addresses?|[:;,{}()\[\]]", " ", no_mail).split()) <= 2:
        return "email", emails, None, []
    if not aff.AFF_WORDS.search(no_mail) and looks_like_names(b.marked):
        return "author", emails, None, split_names(b.marked)
    if aff.AFF_WORDS.search(no_mail):
        # "John Smith, University of X": names first, affiliation after
        parts = b.marked.split(",")
        lead = 0
        while lead < len(parts) and looks_like_names(parts[lead]):
            lead += 1
        if 0 < lead < len(parts):
            names = split_names(",".join(parts[:lead]))
            return "author_aff", emails, aff.strip_noise(",".join(parts[lead:])), names
        return "affiliation", emails, None, []
    if aff.ends_with_country(no_mail) or re.match(r"^\s*\^\{[^}]+\}", b.marked):
        return "affiliation", emails, None, []
    if emails:
        return "email", emails, None, []
    return "other", emails, None, []


def find_title(z: Zones) -> tuple[Optional[str], list[Block]]:
    blocks = [b for b in z.header if re.search(r"[A-Za-z]{2}", b.text) and not NOISE.search(b.text)]
    styled = [b for b in blocks if b.style and b.style.lower() == "title"]
    if styled:
        return _title_text(styled), styled
    tiers = sorted({round(b.font_size * 2) / 2 for b in blocks}, reverse=True)
    for size in tiers[:3]:
        run: list[Block] = []
        for b in blocks:
            same = abs(b.font_size - size) <= 0.6
            if same and (not run or _adjacent(run[-1], b, size)):
                run.append(b)
            elif run:
                break
        text = _title_text(run)
        words = len(text.split())
        if 3 <= words <= 40 and not find_emails(text) and not (aff.AFF_WORDS.search(text) and words < 8 and not run[0].bold):
            return text, run
    return None, []


def _adjacent(a: Block, b: Block, size: float) -> bool:
    if a.bbox is None or b.bbox is None:
        return True
    # Line boxes of big type overlap, so compare tops: next line starts within ~2 lines.
    return a.page == b.page and -2 <= b.bbox[1] - a.bbox[1] < 2.2 * size


def _title_text(blocks: list[Block]) -> str:
    text = join_lines(strip_markers(b.marked) for b in blocks)
    return collapse(re.sub("[" + SYMBOLS + "]", "", text)).strip(" .")


def parse(z: Zones) -> Header:
    h = Header()
    h.title, h.title_blocks = find_title(z)
    title_ids = {id(b) for b in h.title_blocks}
    first_title = min((z.header.index(b) for b in h.title_blocks), default=-1)
    all_blocks = [(b, False) for b in z.header] + [(b, True) for b in footnote_notes(z.footnotes)]
    i = -1
    for b0, foot in all_blocks:
        i += 1
        if id(b0) in title_ids:
            continue
        kind0 = classify(b0)[0]
        parts = [b0]
        if kind0 not in ("author", "author_aff") and len(MARKER_START.findall(b0.marked)) >= 2:
            parts = [_sub_block(b0, s) for s in split_notes(b0.marked)]   # "¹Univ A, India ²Univ B, UK"
        for b in parts:
            kind, emails, aff_text, names = classify(b)
            if not foot and i < first_title and kind not in ("email", "affiliation"):
                kind = "noise"     # journal names and banners above the title
            if foot and kind == "author":
                kind = "other"     # footnotes never introduce new authors
            h.lines.append(Line(block=b, kind=kind, index=i, emails=emails, names=names, aff_text=aff_text, in_footnote=foot))
            h.emails += [e for e in emails if e.lower() not in {x.lower() for x in h.emails}]

    for ln in h.lines:
        if ln.kind in ("author", "author_aff"):
            for name, markers, offset in ln.names:
                if is_name(name):
                    h.authors.append(Author(name=name, markers=markers, line=ln, offset=offset))
    h.affiliations = build_affiliations(h.lines)
    h.double_blind = bool(BLIND.search(" ".join(b.text for b in z.header))) and len(h.authors) == 0
    return h


MARKER_START = re.compile(r"\^\{[^}]+\}\s*[A-Z]")
NOTE_SPLIT = re.compile(r"(?=\^\{[^}]+\}\s*[A-Z])|(?=✉)|\n(?=[" + SYMBOLS + r"])")


def split_notes(marked: str) -> list[str]:
    """'¹Deepmind, London, UK. ²Google, ... ³These authors contributed equally'
    -> one string per note. Splits at each marker followed by a capital, at ✉,
    and at a new line starting with a footnote symbol."""
    return [join_lines(p.split("\n")) for p in NOTE_SPLIT.split(marked) if p.strip()]


def _sub_block(b: Block, marked: str) -> Block:
    return Block(text=strip_markers(marked), marked=marked, page=b.page, bbox=b.bbox, font_size=b.font_size, bold=b.bold, style=b.style)


def footnote_notes(footnotes: list[Block]) -> list[Block]:
    """Page-1 footnotes often run several notes together across lines; rejoin
    the lines, then cut them into one block per note."""
    if not footnotes:
        return []
    joined = "\n".join(b.marked for b in footnotes)
    return [_sub_block(footnotes[0], s) for s in split_notes(joined)]


def build_affiliations(lines: list[Line]) -> list[AffEntry]:
    entries: list[AffEntry] = []
    prev_aff = False
    for ln in lines:
        if ln.kind not in ("affiliation", "author_aff"):
            prev_aff = False if ln.kind not in ("email",) else prev_aff
            continue
        marked = ln.block.marked if ln.kind == "affiliation" else (ln.aff_text or "")
        lead = re.match(r"^\s*\^\{([^}]+)\}\s*", marked) or re.match(r"^\s*(\d{1,2}|[a-z])\s+(?=[A-Z])", marked)
        if lead:
            ln.aff_text = strip_markers(marked[lead.end():])
            entries.append(AffEntry(markers=[m.strip() for m in lead.group(1).split(",") if m.strip()], lines=[ln]))
        elif ln.kind == "affiliation" and entries and prev_aff and not aff.ends_with_country(entries[-1].lines[-1].aff_text or entries[-1].lines[-1].block.text):
            ln.aff_text = strip_markers(marked)
            entries[-1].lines.append(ln)
        else:
            ln.aff_text = strip_markers(marked)
            entries.append(AffEntry(markers=[], lines=[ln]))
        prev_aff = ln.kind == "affiliation"
    return [e for e in entries if e.text]
