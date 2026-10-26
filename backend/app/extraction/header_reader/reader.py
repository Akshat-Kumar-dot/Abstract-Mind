"""Read a paper's header: title, authors, affiliations, emails, corresponding
author, with the links between them and checks. Runs on this machine only.

    read_pdf(bytes) -> Paper

Steps (each adds one line to paper.trace, so a wrong value can be traced to
the step that produced it):
    1 layout        page 1 in reading order
    2 title         largest text near the top
    3 authors       name lines under the title (list or blocks)
    4 affiliations  markers / blocks / "is with" notes / single affiliation
    5 emails        found, then linked to people by the strongest evidence
    6 corresponding marked *, ✉ or named in a correspondence note
    7 checks
"""
from __future__ import annotations

import re

from ..core.models import Document
from ..ingest.pdf import load_pdf
from . import affiliations, checks, emails
from .header import Person, find_authors, find_title, region_under
from .layout import Line, lines_of
from .model import Affiliation, Author, Email, Paper

CORR_SYMBOLS = "*∗⁎✉"
CORR_NOTE = re.compile(r"correspond(ing|ence)", re.I)
EMAIL_LIST = re.compile(r"^\W*e-?mail\s+addresses", re.I)
EQUAL_NOTE = re.compile(r"contributed\s+equally|equal\s+contribution|joint\s+first", re.I)


def pages_needed(count: int) -> set[int]:
    """The header is on page 1; affiliations and addresses can be on page 2 or at the end."""
    return {p for p in (1, 2, count - 1, count) if 1 <= p <= count}


def read_pdf(data: bytes) -> Paper:
    return read_document(load_pdf(data, only_pages=pages_needed))


def read_document(doc: Document) -> Paper:
    paper = Paper()
    page1 = lines_of(doc, 1)
    later = sorted(pages_needed(doc.pages or 1) - {1})
    other = [lines_of(doc, p) for p in later]
    pages = [page1] + other
    all_lines = [ln for page in pages for ln in page]
    paper.trace.append(f"layout: {len(page1)} lines on page 1, {len(all_lines) - len(page1)} on pages {later}")

    # 2 title
    title = find_title(page1)
    paper.title = " ".join(t.text for t in title).replace("- ", "-").strip()
    paper.trace.append(f"title: {paper.title[:80]!r}" if title else "title: not found")
    if not title:
        paper.checks = checks.run(paper, _text(doc))
        return paper

    # 3 authors
    region = region_under(title, page1)
    people, layout = find_authors(region)
    paper.trace.append(f"authors: {len(people)} found, {layout} layout")

    # 4 affiliations
    ends = affiliations.end_addresses(all_lines)                     # a one-page paper ends on page 1
    ends = ends if people and len(ends) == len(people) else []      # trusted only when one per author
    note = {}                                                         # ACM "Authors' addresses: Name, email, place; …"
    for name, place, mails in affiliations.address_note(all_lines):
        p = next((q for q in people if _same_person(q.name, name)), None)
        if p:
            note[p.name] = (place, mails)
    aff_of = _affiliations(paper, people, layout, region, pages, page1, ends, note)

    # 5 emails
    found = emails.find(page1 + [ln for page in other[-2:] for ln in page])
    statements = affiliations.by_statements(page1)
    given = emails.link(people, found, statements, all_lines)
    for p, (_, address) in zip(people, ends):                         # AMS: the address block says whose
        if address not in {e for e, _ in given.values()}:
            given[p.name] = (address, "address block at the end, in author order")
    for name, (_, mails) in note.items():                             # ACM: the address note names its owner
        if mails and name not in given and mails[0] not in {e for e, _ in given.values()}:
            given[name] = (mails[0], "in the authors' addresses note, after the name")
    paper.trace.append(f"emails: {len(found)} found, {len(given)} linked")

    # build the linked records
    for i, p in enumerate(people, 1):
        paper.authors.append(Author(id=f"A{i}", name=p.name, markers=p.markers, affiliation_ids=aff_of.get(p.name, []),
                                    source=p.line.text))
    by_name = {a.name: a for a in paper.authors}
    for i, (address, _) in enumerate(found, 1):
        owner = next((name for name, (e, _) in given.items() if e == address), None)
        how = given[owner][1] if owner else ""
        paper.emails.append(Email(id=f"E{i}", address=address, author_id=by_name[owner].id if owner else None, how=how))
        if owner:
            by_name[owner].email_id = f"E{i}"

    # 6 corresponding
    _corresponding(paper, people, all_lines, found)
    paper.trace.append(f"corresponding: {', '.join(a.name for a in paper.authors if a.corresponding) or 'none marked'}")

    # 7 checks
    paper.checks = checks.run(paper, _text(doc))
    return paper


def _affiliations(paper: Paper, people: list[Person], layout: str, region: list[Line], pages: list[list[Line]],
                  page1: list[Line], ends: list[tuple[str, str]], note: dict) -> dict[str, list[str]]:
    """Fill paper.affiliations; return person name -> affiliation ids."""
    aff_of: dict[str, list[str]] = {}

    def add(text: str, marker: str | None = None) -> str:
        existing = next((f for f in paper.affiliations if f.text == text), None)
        if existing:
            return existing.id
        fid = f"F{len(paper.affiliations) + 1}"
        paper.affiliations.append(Affiliation(id=fid, text=text, marker=marker, source=text))
        return fid

    if layout == "blocks":
        for name, text in affiliations.by_blocks(people).items():
            aff_of[name] = [add(text)]
        paper.trace.append(f"affiliations: {len(paper.affiliations)} from author blocks")
        return aff_of

    entries, footnotes, unmarked, where = affiliations.by_markers(people, pages)
    paper.footnotes.update(footnotes)
    if entries:
        ids = {m: add(t, m) for m, t in entries.items()}
        unmarked_id = add(unmarked) if unmarked else None
        for p in people:
            mine = [ids[m] for m in p.markers if m in ids]
            if not mine and not any(m.isalnum() and m not in footnotes for m in p.markers) and unmarked_id:
                mine = [unmarked_id]
            aff_of[p.name] = mine
        paper.trace.append(f"affiliations: {len(entries)} by markers on {where}" + (", 1 unmarked" if unmarked_id else ""))
        return aff_of

    if note and len(note) == len(people):
        for p in people:
            aff_of[p.name] = [add(note[p.name][0])]
        paper.trace.append(f"affiliations: {len(note)} from the authors' addresses note")
        return aff_of

    if layout == "inline":
        for p in people:
            aff_of[p.name] = [add(p.inline_place)]
        paper.trace.append(f"affiliations: {len(people)} printed after each name")
        return aff_of

    if ends:
        for p, (text, _) in zip(people, ends):
            aff_of[p.name] = [add(text)]
        paper.trace.append(f"affiliations: {len(ends)} address blocks at the end, in author order")
        return aff_of

    statements = affiliations.by_statements(page1)
    if statements:
        for names, text, _ in statements:
            fid = add(text)
            for n in names:
                p = next((q for q in people if _same_person(q.name, n)), None)
                if p:
                    aff_of.setdefault(p.name, []).append(fid)
        paper.trace.append(f"affiliations: {len(statements)} from 'is with' notes")
        return aff_of

    if people:
        author_rows = [ln for p in people for ln in (p.rows or [p.line])]
        found = affiliations.unmarked_entries(region, max(author_rows, key=lambda ln: ln.y0))
        if len(found) == 1:
            fid = add(found[0])
            for p in people:
                aff_of[p.name] = [fid]
            paper.trace.append("affiliations: one, shared by everyone")
        else:
            for t in found:
                add(t)
            paper.trace.append(f"affiliations: {len(found)} without markers; not linked (no way to tell who is where)")
    return aff_of


def _same_person(a: str, b: str) -> bool:
    from rapidfuzz import fuzz
    return fuzz.token_sort_ratio(a.lower(), b.lower()) >= 85


def _corresponding(paper: Paper, people: list[Person], lines: list[Line], found) -> None:
    text = " ".join(ln.text for ln in lines)
    equal_symbols = {s for s in "*∗⁎†‡#§" if re.search(re.escape(s) + r"\s*\w*\s*(?:these authors )?" + EQUAL_NOTE.pattern, text, re.I)}
    corr_markers = {m for m, note in paper.footnotes.items() if CORR_NOTE.search(note) or "whom" in note.lower()}
    for a in paper.authors:
        if any(m in CORR_SYMBOLS and m not in equal_symbols for m in a.markers) or corr_markers & set(a.markers):
            a.corresponding = True
    # named in a correspondence note: "Correspondence: Name, email" / "Corresponding author: Name".
    # Only when no mark said it already: an "Email addresses:" list after the note names everyone.
    if any(a.corresponding for a in paper.authors):
        return
    for i, ln in enumerate(lines):
        if CORR_NOTE.search(ln.text):
            window = []
            for x in lines[i:i + 8]:
                if x.page != ln.page or (window and EMAIL_LIST.match(x.text)):
                    break
                window.append(x.text)
            window = " ".join(window)
            for a in paper.authors:
                if a.name.lower() in window.lower() or (paper.email_of(a) and paper.email_of(a) in window.lower()):
                    a.corresponding = True


def _text(doc: Document) -> str:
    return "\n".join(b.text for b in doc.blocks)
