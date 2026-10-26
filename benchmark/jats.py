"""Turn a publisher's JATS XML (the file PubMed Central keeps next to each PDF)
into the true answers for that paper: title, authors in order, each author's
affiliations, emails and corresponding flag."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET


SKIP = {"label", "institution-id", "ext-link"}          # markers and registry ids (ROR, GRID)
PARTS = {"institution", "institution-wrap", "addr-line", "city", "state", "postal-code", "country", "named-content"}


def _text(el, sep: bool = False) -> str:
    """All text inside an element, spaces normalised. Markers and registry ids
    are dropped; with sep=True the parts of an affiliation are kept apart by commas."""
    if el is None:
        return ""
    parts = [el.text or ""]
    for child in el:
        if child.tag not in SKIP:
            inner = _text(child, sep)
            parts.append(f", {inner}, " if sep and child.tag in PARTS else inner)
        parts.append(child.tail or "")
    text = re.sub(r"\s+", " ", "".join(parts))
    text = re.sub(r"\s*,(\s*,)+", ",", text)                 # collapse the doubled commas
    return re.sub(r"\s+,", ",", text).strip(" ,;")


def _affiliation_text(aff) -> str:
    # some publishers leave the marker as plain text: "a, Oak Ridge Institute…" / "1 Department…"
    return re.sub(r"^(?:[a-z]|\d{1,2})\s*[,.)]?\s+(?=[A-ZÀ-ɏ])", "", _text(aff, sep=True))


def parse(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)
    meta = root.find(".//article-meta")
    title = _text(meta.find(".//title-group/article-title"))

    affs = {a.get("id"): _affiliation_text(a) for a in root.iter("aff") if a.get("id")}
    all_affs = [_affiliation_text(a) for a in root.iter("aff")]
    corresp_notes = {c.get("id"): c for c in root.iter("corresp") if c.get("id")}

    authors = []
    for contrib in meta.iter("contrib"):
        if contrib.get("contrib-type") != "author" or contrib.find("collab") is not None:
            continue
        name_el = contrib.find("name")
        if name_el is None:
            continue
        given, family = _text(name_el.find("given-names")), _text(name_el.find("surname"))
        emails = [_text(e) for e in contrib.iter("email")]
        aff_texts, corresponding = [], contrib.get("corresp") == "yes"
        for x in contrib.iter("xref"):
            rid = x.get("rid") or ""
            if x.get("ref-type") == "aff":
                for r in rid.split():
                    if r in affs:
                        aff_texts.append(affs[r])
            elif x.get("ref-type") == "corresp":
                corresponding = True
                note = corresp_notes.get(rid)
                if note is not None and not emails:
                    found = [_text(e) for e in note.iter("email")]
                    if len(found) == 1:
                        emails = found
        for aff in contrib.iter("aff"):                     # affiliation written inside the author
            aff_texts.append(_affiliation_text(aff))
        authors.append({"given": given, "family": family, "name": f"{given} {family}".strip(),
                        "emails": sorted(set(e.lower() for e in emails if "@" in e)),
                        "affiliations": aff_texts, "corresponding": corresponding})

    # One affiliation for everyone, without links: every author has it.
    if authors and not any(a["affiliations"] for a in authors) and len(all_affs) == 1:
        for a in authors:
            a["affiliations"] = list(all_affs)

    journal = _text(root.find(".//journal-meta//journal-title"))
    return {"title": title, "journal": journal, "authors": authors}
