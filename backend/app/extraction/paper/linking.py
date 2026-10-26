"""Linking authors to affiliations, emails, ORCID iDs and the corresponding-author
mark. Methods are tried from strongest to weakest; nothing is guessed by order."""
from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import fuzz

from ..core.models import Document
from ..core.text import ORCID_RE, ascii_fold, find_emails, join_lines
from ..core.verify import orcid_ok
from . import affiliations as aff
from .header import STATEMENT, SYMBOLS, Author, Header, Line, split_notes
from .zones import Zones


def link(h: Header, z: Zones, doc: Optional[Document] = None) -> None:
    if not h.authors:
        return
    for a in h.authors:
        if a.line.kind == "author_aff" and a.line.aff_text:
            _add(a, a.line.aff_text, "same line")
    if _block_layout(h):
        _link_layout(h)
    _link_markers(h)
    _link_end_affiliations(h, z)
    _link_statements(h, z)
    if any(not a.affiliations for a in h.authors):
        _link_interleaved(h) or _link_single(h)
    for a in h.authors:
        a.affiliation_parts = [aff.parse(t) for t in a.affiliations]
    _link_emails(h, doc)
    _link_corresponding(h)
    _link_orcid(h, doc)


def _add(a: Author, text: str, mode: str) -> None:
    text = aff.strip_noise(text)
    if text and text not in a.affiliations:
        a.affiliations.append(text)
        a.link_mode = a.link_mode or mode


# ------------------------------------------------------------ affiliations

def _author_lines(h: Header) -> list[Line]:
    seen, out = set(), []
    for a in h.authors:
        if id(a.line) not in seen:
            seen.add(id(a.line))
            out.append(a.line)
    return out


def _block_layout(h: Header) -> bool:
    """IEEE style: author blocks side by side, each with its affiliation below."""
    lines = [ln for ln in _author_lines(h) if ln.block.bbox and not ln.in_footnote]
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            if a.block.page == b.block.page and abs(a.block.bbox[1] - b.block.bbox[1]) < 3:
                return True
    return False


def _overlap(a, b) -> float:
    inter = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    return inter / max(1.0, b[2] - b[0])


def _link_layout(h: Header) -> None:
    author_lines = [ln for ln in _author_lines(h) if ln.block.bbox]
    collected: dict[int, list[Line]] = {}
    for ln in h.lines:
        if ln.in_footnote or ln.kind in ("author", "author_aff", "noise", "corr_note", "equal_note", "statement") or not ln.block.bbox:
            continue
        bb = ln.block.bbox
        above = [a for a in author_lines if a.block.page == ln.block.page and a.block.bbox[3] <= bb[1] + 2]
        if not above:
            continue
        nearest = max(a.block.bbox[3] for a in above)
        row = [a for a in above if abs(a.block.bbox[3] - nearest) < 4]
        best = max(row, key=lambda a: _overlap(a.block.bbox, bb))
        if _overlap(best.block.bbox, bb) < 0.3:
            continue
        collected.setdefault(id(best), []).append(ln)
    for a in h.authors:
        lines = collected.get(id(a.line), [])
        mine = [a2 for a2 in h.authors if a2.line is a.line]
        text = ", ".join(aff.strip_noise(ln.block.text) for ln in lines if ln.kind != "email" and aff.strip_noise(ln.block.text))
        if text:
            _add(a, text, "layout")
        emails = [e for ln in lines for e in ln.emails]
        if len(mine) == 1 and len(emails) == 1:
            a.email, a.email_how = emails[0], "layout"


def _link_markers(h: Header) -> None:
    table: dict[str, list[str]] = {}
    for e in h.affiliations:
        for m in e.markers:
            table.setdefault(m, []).append(e.text)
    if not table:
        return
    for a in h.authors:
        for m in a.markers:
            for text in table.get(m, []):
                _add(a, text, "markers")


def _link_end_affiliations(h: Header, z: Zones) -> None:
    """Nature, Science and Cell often list numbered affiliations at the end of
    the article. Used only for author markers that page 1 did not explain."""
    known = {m for e in h.affiliations for m in e.markers}
    meanings = _symbol_meanings(h)
    wanted = {m for a in h.authors for m in a.markers if m.isalnum() and m not in known and m not in meanings}
    if not wanted:
        return
    found: dict[str, str] = {}
    last: str | None = None
    for b in z.body + z.references + z.tail:
        if (b.page or 1) < 2:
            continue
        marked = re.sub(r"^\s*(\d{1,3})(?=[A-Z][a-z])", r"^{\1}", b.marked)    # "12Department" lost its superscript
        notes = split_notes(marked)
        for note in notes:
            m = re.match(r"^\s*\^\{([^}]+)\}\s*(.+)", note)
            if m and m.group(1).strip() in wanted and aff.looks_like_affiliation(m.group(2)):
                last = m.group(1).strip()
                found.setdefault(last, aff.strip_noise(m.group(2)))
            elif not m and last and len(notes) == 1 and not aff.ends_with_country(found[last]) and aff.looks_like_affiliation(note):
                found[last] = aff.strip_noise(found[last] + ", " + note)   # wrapped line
            else:
                last = None
    for a in h.authors:
        for m in a.markers:
            if m in found:
                _add(a, found[m], "markers (end of paper)")


def parse_statements(text: str) -> list[tuple[str, str, list[str]]]:
    """IEEE journals: 'A. Kumar and R. Mehta are with the Department of ...
    (e-mail: ...)'. Returns (who, where, emails) per sentence."""
    out = []
    for sentence in re.split(r"(?<=[.)])\s+(?=[A-Z])", text):
        m = STATEMENT.search(sentence)
        if not m:
            continue
        who, where = sentence[:m.start()], sentence[m.end():]
        mail = re.search(r"\(?\s*e-?mails?\s*:?([^)]*)\)?", where, re.I)
        emails = find_emails(mail.group(1)) if mail else []
        where = re.sub(r"\(?\s*e-?mails?\s*:?[^)]*\)?", "", where, flags=re.I).strip(" .;")
        out.append((who, where, emails))
    return out


def _link_statements(h: Header, z: Zones) -> None:
    text = join_lines([ln.block.text for ln in h.lines if ln.kind in ("statement",) or ln.in_footnote])
    for who, where, emails in parse_statements(text):
        targets = [a for a in h.authors if _name_in(a.name, who)]
        for a in targets:
            _add(a, where, "statement")
            if len(targets) == 1 and emails and not a.email:
                a.email, a.email_how = emails[0], "statement"


def _name_in(name: str, text: str) -> bool:
    last = name.split()[-1]
    return bool(re.search(r"\b" + re.escape(last) + r"\b", text))


def _link_interleaved(h: Header) -> bool:
    """'Name / affiliation / Name / affiliation' with no markers."""
    kinds = [ln.kind for ln in h.lines if not ln.in_footnote and ln.kind in ("author", "affiliation")]
    seq = "".join("A" if k == "author" else "F" for k in kinds)
    if not re.search(r"AF+A", seq):
        return False
    current: list[Author] = []
    for ln in h.lines:
        if ln.in_footnote:
            continue
        if ln.kind == "author":
            current = [a for a in h.authors if a.line is ln]
        elif ln.kind == "affiliation" and current:
            for a in current:
                if a.link_mode in (None, "interleaved"):
                    _add(a, ln.aff_text or ln.block.text, "interleaved")
                    a.link_mode = "interleaved"
    return True


def _link_single(h: Header) -> bool:
    unmarked = [e for e in h.affiliations if not e.markers]
    if len(h.affiliations) == 1 or (len(unmarked) == 1 and not any(e.markers for e in h.affiliations)):
        text = (unmarked or h.affiliations)[0].text
        for a in h.authors:
            if not a.affiliations:
                _add(a, text, "single affiliation")
        return True
    return False


# ------------------------------------------------------------ emails

def _variants(name: str) -> list[str]:
    toks = [re.sub(r"[^a-z]", "", t) for t in ascii_fold(name).lower().split()]
    toks = [t for t in toks if t]
    if not toks:
        return []
    f, l = toks[0], toks[-1]
    inits = "".join(t[0] for t in toks[:-1])
    return [f + l, f + "." + l, f + "_" + l, f + "-" + l, f[0] + l, f[0] + "." + l, l + f[0], l, f, l + f, l + "." + f, f + l[0], inits + l]


def email_score(name: str, email: str) -> float:
    local = re.sub(r"\d+$", "", email.split("@")[0].lower())
    return max((fuzz.ratio(local, v) for v in _variants(name)), default=0)


def _link_emails(h: Header, doc: Optional[Document]) -> None:
    emails = list(h.emails)
    if doc is not None:
        for ln in doc.links:
            if ln["page"] == 1 and ln["uri"].lower().startswith("mailto:"):
                e = ln["uri"][7:].split("?")[0]
                if e.lower() not in {x.lower() for x in emails}:
                    emails.append(e)
    taken = {a.email.lower() for a in h.authors if a.email}
    free = [e for e in emails if e.lower() not in taken]
    names = [None if a.email else a.name for a in h.authors]
    for ai, (email, how) in match_emails(names, free).items():
        h.authors[ai].email, h.authors[ai].email_how = email, how


def match_emails(names: list[Optional[str]], emails: list[str]) -> dict[int, tuple[str, str]]:
    """Best one-to-one pairing of emails to names (None = already has one)."""
    if not emails:
        return {}
    pairs = sorted(((email_score(n, e), ai, ei) for ai, n in enumerate(names) if n for ei, e in enumerate(emails)), reverse=True)
    out: dict[int, tuple[str, str]] = {}
    used_e = set()
    for s, ai, ei in pairs:
        if s < 60 or ai in out or ei in used_e:
            continue
        out[ai] = (emails[ei], "name match")
        used_e.add(ei)
    if len(names) == 1 and names[0] and 0 not in out and len(emails) == 1:
        out[0] = (emails[0], "only author")
    return out


# ------------------------------------------------------------ corresponding

def _symbol_meanings(h: Header) -> dict[str, str]:
    meanings: dict[str, str] = {}
    for ln in h.lines:
        if ln.kind not in ("corr_note", "equal_note"):
            continue
        # The note's own marker tells what that marker means on author names:
        # "³These authors contributed equally", "*Corresponding author"
        m = re.match(r"^\s*(?:\^\{([^}]+)\}|([" + SYMBOLS + r"]))", ln.block.marked)
        if m:
            keys = m.group(1).split(",") if m.group(1) else [m.group(2)]
            for k in keys:
                meanings[k.strip()] = "corresponding" if ln.kind == "corr_note" else "equal"
    return meanings


def _link_corresponding(h: Header) -> None:
    meanings = _symbol_meanings(h)
    for sym in "*∗✉":
        meanings.setdefault(sym, "corresponding")
    for a in h.authors:
        for m in a.markers:
            if meanings.get(m) == "corresponding":
                a.corresponding, a.corresponding_how = True, f"marked {m}"
            elif meanings.get(m) == "equal":
                a.equal = True
    if any(a.corresponding for a in h.authors):
        return
    for ln in h.lines:
        if ln.kind != "corr_note":
            continue
        for a in h.authors:
            if (a.email and a.email.lower() in ln.block.text.lower()) or _name_in(a.name, ln.block.text):
                a.corresponding, a.corresponding_how = True, "corresponding-author note"
        for e in ln.emails:
            for a in h.authors:
                if not a.email and email_score(a.name, e) >= 60:
                    a.email, a.email_how = e, "corresponding-author note"
                    a.corresponding, a.corresponding_how = True, "corresponding-author note"
    if any(a.corresponding for a in h.authors):
        return
    with_email = [a for a in h.authors if a.email]
    if len(with_email) == 1 and len(h.authors) > 1:
        with_email[0].corresponding, with_email[0].corresponding_how = True, "only author with an email"


# ------------------------------------------------------------ ORCID

def _link_orcid(h: Header, doc: Optional[Document]) -> None:
    for ln in h.lines:
        for oid in ORCID_RE.findall(ln.block.text):
            if not orcid_ok(oid):
                continue
            here = [a for a in h.authors if _name_in(a.name, ln.block.text)]
            if len(here) == 1 and not here[0].orcid:
                here[0].orcid = oid
    if doc is None:
        return
    for link in doc.links:
        m = re.search(r"orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", link["uri"])
        if not m or link["page"] != 1 or not orcid_ok(m.group(1)):
            continue
        best, dist = None, float("inf")
        lx = (link["rect"][0] + link["rect"][2]) / 2
        ly = (link["rect"][1] + link["rect"][3]) / 2
        for a in h.authors:
            bb = a.line.block.bbox
            if not bb:
                continue
            frac = a.offset / max(1, len(a.line.block.text))
            ax = bb[0] + (bb[2] - bb[0]) * frac
            d = abs(ly - (bb[1] + bb[3]) / 2) * 3 + abs(lx - ax)
            if lx < ax - 5:
                d += 50   # the iD icon follows the name
            if d < dist:
                best, dist = a, d
        if best is not None and not best.orcid:
            best.orcid = m.group(1)
