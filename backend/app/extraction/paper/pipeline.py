"""Manuscript pipeline: zones -> header -> linking -> scoring -> LLM gaps ->
declarations and counts -> fields with confidence."""
from __future__ import annotations

import re
from typing import Optional

from ..core.confidence import make
from ..core.models import Block, Document, Evidence, Field, Result, evidence_of, group
from ..core.text import count_words, join_lines
from ..core.verify import email_ok, orcid_ok
from ..ingest import layout
from . import affiliations as aff
from . import authors as scoring
from . import declarations, header, linking, llm_fill, publication, stats, zones
from .header import Author, Header, Line
from .names import split_name

AUTHOR_LINK_BASE = {"markers": 0.92, "markers (end of paper)": 0.86, "layout": 0.9, "same line": 0.9, "statement": 0.88, "single affiliation": 0.86,
                    "interleaved": 0.78, "LLM": 0.75, "tex": 0.98}
EMAIL_BASE = {"layout": 0.9, "statement": 0.9, "only author": 0.88, "name match": 0.85, "corresponding-author note": 0.85,
              "LLM": 0.75, "tex": 0.98}
CORR_BASE = {"LLM": 0.72, "only author with an email": 0.65, "tex": 0.95}


def run(doc: Document, allow_ai: bool = False) -> Result:
    res = Result(kind="paper", file_type=doc.source, pages=doc.pages, warnings=list(doc.warnings))
    if doc.source == "tex":
        return _run_tex(doc, res)
    pub = publication.find(doc)          # before clean-up removes running footers
    layout.clean(doc)
    z = zones.split(doc)
    h = header.parse(z)
    linking.link(h, z, doc)
    scoring.apply(h)
    res.llm, keywords = llm_fill.fill(h, z, z.keywords, allow_ai=allow_ai)
    for a in h.authors:
        if a.affiliations and not a.affiliation_parts:
            a.affiliation_parts = [aff.parse(t) for t in a.affiliations]
    scoring.apply(h)
    decl = declarations.find(z.body + z.tail, z.body_size)
    st = stats.compute(doc, z)

    title_ev = Evidence(h.title_blocks[0].page, h.title) if h.title_blocks and h.title else None
    res.groups = [
        group("paper", "Paper", [
            make("title", "Title", h.title, h.title_source, evidence=title_ev,
                 failed=0 if not h.title or 3 <= len(h.title.split()) <= 40 else 1),
            _abstract_field(z.abstract, z.abstract_block, inferred=z.abstract_inferred),
            make("keywords", "Keywords", keywords, "rule" if z.keywords else "llm", evidence=evidence_of(z.keywords_block)),
        ]),
        _declarations_group(decl),
        _stats_group(st, doc),
    ]
    if pub.found:
        res.groups.insert(1, _publication_group(pub))
    res.authors = [_author_card(i, a, h) for i, a in enumerate(h.authors, start=1)]
    _warnings(res, h, z)
    return res


# ---------------------------------------------------------------- fields

def _abstract_field(text: Optional[str], block: Optional[Block], source: str = "rule", inferred: bool = False) -> Field:
    words = count_words(text or "")
    failed = 0 if not text or source == "tex" or 25 <= words <= 700 else 1
    note = f"{words} words" if text else None
    if inferred and text:
        note += "; no 'Abstract' heading, so the opening paragraph was taken"
    return make("abstract", "Abstract", text, source, base=0.72 if inferred else None, evidence=evidence_of(block),
                long=True, failed=failed, note=note)


def _publication_group(p: publication.Publication) -> dict:
    labels = {"received": "Received", "revised": "Revised", "accepted": "Accepted", "published": "Published"}
    fields = [
        make("doi", "DOI", p.doi, "rule", base=0.95, evidence=publication.evidence(p, "doi")),
        make("publisher", "Publisher", p.publisher, "rule", base=0.9, note="From the DOI prefix" if p.publisher else None),
        make("journal", "Journal / venue", p.journal, "rule", base=0.75, evidence=publication.evidence(p, "journal"),
             note=f"From the running footer: {p.journal_line}" if p.journal_line else None),
        make("volume", "Volume", p.volume, "rule", base=0.85, evidence=publication.evidence(p, "journal")),
    ]
    for key, label in labels.items():
        if key in p.dates:
            fields.append(make(key, label, p.dates[key], "rule", base=0.9, evidence=publication.evidence(p, key)))
    return group("publication", "Publication", fields)


def _declarations_group(d: declarations.Declarations) -> dict:
    def sec(kind: str) -> tuple[Optional[str], Optional[Evidence]]:
        s = d.sections.get(kind)
        return (s.text, evidence_of(s.block)) if s else (None, None)

    funding_ev = evidence_of(d.funding_block)
    fields = [
        make("funding", "Funding statement", d.funding_text, "rule", evidence=funding_ev, long=True,
             note=None if "funding" in d.sections or not d.funding_text else "Taken from the acknowledgments"),
        make("grant_ids", "Grant numbers", d.grant_ids, "rule", base=0.8, evidence=funding_ev),
    ]
    for kind, label in (("conflicts", "Conflicts of interest"), ("data", "Data availability"),
                        ("contributions", "Author contributions"), ("ethics", "Ethics statement"),
                        ("acknowledgments", "Acknowledgments")):
        text, ev = sec(kind)
        fields.append(make(kind, label, text, "rule", evidence=ev, long=True))
        if kind == "data":
            fields.append(make("data_urls", "Data / code links", d.data_urls, "rule", evidence=ev))
        if kind == "contributions" and d.credit_roles:
            fields.append(make("credit_roles", "CRediT roles mentioned", d.credit_roles, "rule", evidence=ev))
        if kind == "ethics" and d.approval_ids:
            fields.append(make("approval_ids", "Approval numbers", d.approval_ids, "rule", base=0.8, evidence=ev))
    return group("declarations", "Declarations", fields)


def _stats_group(st: stats.Stats, doc: Document) -> dict:
    pages_note = "From Word's last save" if doc.source == "docx" else None
    if doc.source == "tex":
        pages_note = "LaTeX source has no pages; upload the PDF for a page count"
    return group("stats", "Counts", [
        make("pages", "Pages", st.pages, "count", base=0.88 if doc.source == "docx" else None, note=pages_note),
        make("words_main", "Words (abstract + main text)", st.words_main, "count", base=0.9,
             note="Excludes title, author block and references"),
        make("words_with_refs", "Words (including references)", st.words_with_refs, "count", base=0.9),
        make("figures", "Figures", st.figures, "count", base=0.88, note="Unique figure caption numbers"),
        make("tables", "Tables", st.tables, "count", base=0.88, note="Unique table caption numbers"),
        make("references", "References", st.references, "count",
             base=0.95 if "numbered" in st.references_how else 0.75, note=st.references_how),
    ])


def _author_card(pos: int, a: Author, h: Header) -> dict:
    src = a.source
    failed = a.failed + (1 if a.score < scoring.THRESHOLD and src == "rule" else 0)
    ev = evidence_of(a.line.block) if a.line.kind != "llm" else None
    first, last = split_name(a.name)
    n_tokens = len(a.name.split())
    fields = [
        make("name", "Full name", a.name, src, failed=failed, agreed=a.agreed, evidence=ev, note=a.note),
        make("first_name", "First name", first, "rule", base=0.9 if n_tokens == 2 else 0.72),
        make("last_name", "Last name", last, "rule", base=0.9 if n_tokens == 2 else 0.72),
    ]
    email_ev = _evidence_with(h, a.email) if a.email else None
    email_src = {"tex": "tex", "LLM": "llm"}.get(a.email_how or "", "rule")
    fields.append(make("email", "Email", a.email, email_src, base=EMAIL_BASE.get(a.email_how or "", 0.8),
                       failed=0 if not a.email or email_ok(a.email) else 1, evidence=email_ev,
                       note=f"Linked by {a.email_how}" if a.email_how and a.email_how not in ("layout", "tex") else None))
    orcid_src = src if src in ("tex", "llm", "suggested") else "rule"
    fields.append(make("orcid", "ORCID iD", a.orcid, orcid_src, base=0.95 if src not in ("llm", "suggested") else 0.75,
                       failed=0 if not a.orcid or orcid_ok(a.orcid) else 1))
    aff_note = None
    if not a.affiliations and h.affiliations:
        aff_note = "Affiliations were found but could not be linked to this author"
    elif a.link_mode and a.link_mode not in ("tex", "layout", "markers"):
        aff_note = f"Linked by {a.link_mode}"
    aff_ev = _evidence_with(h, a.affiliations[0]) if a.affiliations else None
    aff_src = {"tex": "tex", "LLM": "llm", "layout": "layout"}.get(a.link_mode or "", "rule")
    fields.append(make("affiliations", "Affiliation(s)", a.affiliations, aff_src, base=AUTHOR_LINK_BASE.get(a.link_mode or "", 0.75),
                       evidence=aff_ev, note=aff_note))
    parts = a.affiliation_parts[0] if a.affiliation_parts else {}
    part_base = 0.98 if a.link_mode == "tex" and parts else 0.74
    for key, label in (("department", "Department"), ("institution", "Institution"), ("city", "City"), ("country", "Country")):
        fields.append(make(key, label, parts.get(key), "tex" if part_base > 0.9 else "rule", base=part_base + (0.12 if key == "country" and part_base < 0.9 else 0)))
    any_corr = any(x.corresponding for x in h.authors)
    if a.corresponding:
        base = 0.95 if (a.corresponding_how or "").startswith("marked") else CORR_BASE.get(a.corresponding_how or "", 0.88)
        fields.append(make("corresponding", "Corresponding author", True, "rule", base=base, note=a.corresponding_how))
    else:
        fields.append(make("corresponding", "Corresponding author", False, "rule", base=0.9 if any_corr else 0.5,
                           note=None if any_corr else "No corresponding-author mark found in the paper"))
    if a.equal:
        fields.append(make("equal", "Equal contribution", True, "rule", base=0.9))
    return {
        "position": pos,
        "name": a.name,
        "corresponding": a.corresponding,
        "score": a.score,
        "fields": [f.to_dict() for f in fields],
    }


def _evidence_with(h: Header, needle: str) -> Optional[Evidence]:
    key = needle.lower()[:40]
    for ln in h.lines:
        if key and key in ln.block.text.lower():
            return evidence_of(ln.block)
    return None


def _warnings(res: Result, h: Header, z: zones.Zones) -> None:
    if h.double_blind:
        res.warnings.append("This looks like a double-blind submission: author names are hidden, so none were extracted.")
    elif not h.authors:
        res.warnings.append("No authors were found in the header.")
    if z.header_found_by == "first paragraph":
        res.notes.append("This paper has no Abstract or Introduction heading; the header was taken as everything above the first paragraph.")
    if z.header_found_by == "layout fallback":
        res.warnings.append("No Abstract or Introduction heading was found, so the header was located by layout. Check the author fields closely.")
    if z.header_found_by == "title page":
        res.notes.append("The paper starts with a separate title page; authors were read from it.")


# ---------------------------------------------------------------- LaTeX

def _run_tex(doc: Document, res: Result) -> Result:
    t = doc.tex or {}
    res.llm = {"provider": None, "used": False, "reason": "Not needed for LaTeX: fields come straight from the source."}
    amap: dict = t.get("affiliation_map", {})
    pmap: dict = t.get("affiliation_parts_map", {})
    h = Header(title=t.get("title"), title_source="tex")
    for x in t.get("authors", []):
        line = Line(block=Block(text=x["name"], marked=x["name"]), kind="tex", index=-1)
        a = Author(name=x["name"], markers=x["markers"], line=line, email=x.get("email"), orcid=x.get("orcid"),
                   affiliations=list(x.get("affiliations", [])), affiliation_parts=list(x.get("affiliation_parts", [])),
                   corresponding=bool(x.get("corresponding")), source="tex")
        for m in a.markers:
            if m in amap and amap[m] not in a.affiliations:
                a.affiliations.append(amap[m])
                if m in pmap:
                    a.affiliation_parts.append(pmap[m])
        if a.email:
            a.email_how = "tex"
        if a.affiliations:
            a.link_mode = "tex"
        if a.corresponding:
            a.corresponding_how = "tex"
        if any(m in ("*", "∗", "✉") for m in a.markers):
            a.corresponding, a.corresponding_how = True, "marked *"
        h.authors.append(a)
    if len(amap) == 1 and not any(a.affiliations for a in h.authors):
        only = next(iter(amap.values()))
        for a in h.authors:
            a.affiliations, a.link_mode = [only], "single affiliation"
    footnotes = join_lines(t.get("footnotes", []))
    for who, where, emails in linking.parse_statements(footnotes):
        targets = [a for a in h.authors if re.search(r"\b" + re.escape(a.name.split()[-1]) + r"\b", who)]
        for a in targets:
            if where and where not in a.affiliations:
                a.affiliations.append(where)
                a.link_mode = a.link_mode or "statement"
            if len(targets) == 1 and emails and not a.email:
                a.email, a.email_how = emails[0], "statement"
    names = [None if a.email else a.name for a in h.authors]
    for ai, (email, how) in linking.match_emails(names, t.get("emails", [])).items():
        h.authors[ai].email, h.authors[ai].email_how = email, how
    if not any(a.corresponding for a in h.authors) and re.search(r"correspond", footnotes, re.I):
        for a in h.authors:
            if re.search(r"\b" + re.escape(a.name.split()[-1]) + r"\b", footnotes):
                a.corresponding, a.corresponding_how = True, "corresponding-author note"
    for a in h.authors:
        parsed = [aff.parse(x) for x in a.affiliations]
        if not a.affiliation_parts:
            a.affiliation_parts = parsed
        else:
            # Keep what the source states (city, country); fill the rest by parsing.
            for given, guess in zip(a.affiliation_parts, parsed):
                for k, v in guess.items():
                    if not given.get(k):
                        given[k] = v
        a.score = 5

    counts = t.get("counts", {})
    body_text = join_lines([t.get("abstract") or ""] + [b.text for b in doc.blocks if b.style != "heading"])
    st = stats.Stats(pages=None, words_main=count_words(body_text), words_with_refs=count_words(body_text),
                     figures=counts.get("figures", 0), tables=counts.get("tables", 0), references=counts.get("references"),
                     references_how=counts.get("references_note") or ("\\bibitem entries" if counts.get("references") is not None else "no bibliography in this file"))
    decl = declarations.find(doc.blocks, 10)
    res.groups = [
        group("paper", "Paper", [
            make("title", "Title", h.title, "tex"),
            make("short_title", "Short / running title", t.get("short_title"), "tex"),
            _abstract_field(t.get("abstract"), None, "tex"),
            make("keywords", "Keywords", t.get("keywords") or [], "tex"),
        ]),
        _declarations_group(decl),
        _stats_group(st, doc),
    ]
    res.authors = [_author_card(i, a, h) for i, a in enumerate(h.authors, start=1)]
    if not h.authors:
        res.warnings.append("No \\author commands were found in this LaTeX file.")
    res.notes.append(f"Read as LaTeX ({t.get('document_class', 'article')} class, {t.get('family')} author commands).")
    return res
