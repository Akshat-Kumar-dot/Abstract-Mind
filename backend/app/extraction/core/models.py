"""Shared shapes. Every input format is turned into a Document of Blocks, so the
algorithms after ingest never care whether the file was a PDF, scan, Word or LaTeX."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

BBox = tuple[float, float, float, float]


@dataclass
class Block:
    text: str                      # plain text, superscript markers removed
    marked: str                    # same text with superscripts kept as ^{...}
    page: Optional[int] = None     # 1-based; None for DOCX/LaTeX
    bbox: Optional[BBox] = None    # PDF points; None when there is no layout
    font_size: float = 0.0
    bold: bool = False
    style: Optional[str] = None    # DOCX style name or LaTeX role
    lead_bold: Optional[str] = None  # bold words opening a line ("Acknowledgements We thank")


@dataclass
class Document:
    source: str                              # "pdf" | "ocr" | "docx" | "tex" | "image"
    blocks: list[Block]
    pages: Optional[int] = None
    page_sizes: dict[int, tuple[float, float]] = field(default_factory=dict)
    links: list[dict] = field(default_factory=list)   # {"page", "uri", "rect"}
    tex: Optional[dict] = None                         # header fields parsed from LaTeX
    warnings: list[str] = field(default_factory=list)


@dataclass
class Evidence:
    page: Optional[int]
    text: str


@dataclass
class Field:
    key: str
    label: str
    value: Any
    source: str = "rule"
    confidence: float = 0.0
    status: str = "missing"
    evidence: Optional[Evidence] = None
    note: Optional[str] = None
    long: bool = False

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "status": self.status,
            "evidence": None if self.evidence is None else {"page": self.evidence.page, "text": self.evidence.text},
            "note": self.note,
            "long": self.long,
        }


def evidence_of(block: Optional[Block], text: Optional[str] = None) -> Optional[Evidence]:
    if block is None:
        return None
    snippet = (text or block.text).strip()
    if len(snippet) > 220:
        snippet = snippet[:217] + "..."
    return Evidence(page=block.page, text=snippet)


@dataclass
class Result:
    kind: str
    file_type: str
    pages: Optional[int]
    groups: list[dict] = field(default_factory=list)
    authors: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)      # informational, not problems
    llm: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "file_type": self.file_type,
            "pages": self.pages,
            "groups": self.groups,
            "authors": self.authors,
            "warnings": self.warnings,
            "notes": self.notes,
            "llm": self.llm,
        }


def group(gid: str, title: str, fields: list[Field]) -> dict:
    return {"id": gid, "title": title, "fields": [f.to_dict() for f in fields]}
