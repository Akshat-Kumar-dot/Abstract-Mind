"""Publication details for papers that are already out: DOI, publisher (from
the DOI prefix), journal line, and the received/accepted/published dates.
Read before layout clean-up, because journal names sit in running footers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..core.models import Block, Document, Evidence, evidence_of

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)")
DATE = r"(\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"
DATES = {
    "received": re.compile(r"\breceived\s*:?\s*(?:on\s+)?" + DATE, re.I),
    "revised": re.compile(r"\brevised\s*(?:version)?\s*:?\s*(?:on\s+)?" + DATE, re.I),
    "accepted": re.compile(r"\baccepted\s*:?\s*(?:on\s+|for\s+publication\s+)?" + DATE, re.I),
    "published": re.compile(r"\b(?:published(?:\s+online)?|available\s+online)\s*:?\s*(?:on\s+)?" + DATE, re.I),
}
JOURNAL_LINE = re.compile(r"\bvol(?:ume)?\.?\s*\d+|\|\s*\d{4}\s*\||\bno\.\s*\d+", re.I)

# DOI prefix -> publisher, for the publishers most papers come from.
PUBLISHERS = {
    "10.1038": "Springer Nature (Nature Portfolio)", "10.1007": "Springer", "10.1186": "BioMed Central (Springer Nature)",
    "10.1016": "Elsevier", "10.1109": "IEEE", "10.1145": "ACM", "10.1002": "Wiley", "10.1111": "Wiley",
    "10.1080": "Taylor & Francis", "10.3390": "MDPI", "10.1371": "PLOS", "10.1126": "AAAS (Science)",
    "10.1093": "Oxford University Press", "10.1017": "Cambridge University Press", "10.1021": "American Chemical Society",
    "10.1103": "American Physical Society", "10.1088": "IOP Publishing", "10.1177": "SAGE", "10.3389": "Frontiers",
    "10.1073": "PNAS", "10.1039": "Royal Society of Chemistry", "10.1063": "AIP Publishing", "10.48550": "arXiv",
    "10.1101": "Cold Spring Harbor Laboratory (bioRxiv/medRxiv)", "10.1155": "Hindawi (Wiley)", "10.1364": "Optica Publishing",
    "10.1049": "IET", "10.1142": "World Scientific", "10.1515": "De Gruyter", "10.18653": "ACL Anthology",
    "10.24963": "IJCAI", "10.1609": "AAAI", "10.5555": "ACM / proceedings", "10.21105": "Journal of Open Source Software",
}


@dataclass
class Publication:
    doi: Optional[str] = None
    doi_block: Optional[Block] = None
    publisher: Optional[str] = None
    journal_line: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    journal_block: Optional[Block] = None
    dates: dict = None
    date_blocks: dict = None

    @property
    def found(self) -> bool:
        return bool(self.doi or self.journal or self.dates)


def find(doc: Document) -> Publication:
    p = Publication(dates={}, date_blocks={})
    early = [b for b in doc.blocks if (b.page or 1) <= 2]
    for b in early:
        if p.doi is None and (m := DOI_RE.search(b.text)):
            p.doi, p.doi_block = m.group(1).rstrip(".,;)"), b
        for key, rx in DATES.items():
            if key not in p.dates and (m := rx.search(b.text)):
                p.dates[key], p.date_blocks[key] = m.group(1), b
    if p.doi is None:
        for link in doc.links:
            if link["page"] <= 1 and (m := DOI_RE.search(link["uri"])):
                p.doi = m.group(1).rstrip(".,;)")
                break
    if p.doi:
        prefix = p.doi.split("/")[0]
        p.publisher = PUBLISHERS.get(prefix)
    for b in early:
        if b.page != 1 or b.bbox is None or not doc.page_sizes:
            continue
        h = doc.page_sizes[1][1]
        in_margin = b.bbox[1] < 0.1 * h or b.bbox[3] > 0.9 * h
        if in_margin and JOURNAL_LINE.search(b.text) and not DOI_RE.search(b.text):
            p.journal_line, p.journal_block = b.text, b
            first = re.split(r"\s*[|,;]\s*|\s+vol", b.text, flags=re.I)[0].strip()
            p.journal = first if re.search(r"[A-Za-z]{3}", first) else None
            if m := re.search(r"\bvol(?:ume)?\.?\s*(\d+)", b.text, re.I):
                p.volume = m.group(1)
            break
    return p


def evidence(p: Publication, key: str) -> Optional[Evidence]:
    if key == "doi":
        return evidence_of(p.doi_block)
    if key == "journal":
        return evidence_of(p.journal_block)
    return evidence_of((p.date_blocks or {}).get(key))
