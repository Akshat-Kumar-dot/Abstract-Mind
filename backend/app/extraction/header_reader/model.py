"""What a paper's header is, with the links between the parts.

    Paper
      authors        A1, A2 …   each points at affiliation ids and an email id
      affiliations   F1, F2 …   each knows its marker ("1", "a", "*") and its text
      emails         E1, E2 …   each points at one author id, and says how it was linked
      checks                    what was verified, and what needs a person's eye

Every value keeps the line of the paper it came from (`source`), so a wrong
value can be traced back to the exact place it was read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Affiliation:
    id: str                          # "F1"
    text: str                        # as printed, joined onto one line
    marker: Optional[str] = None     # "1", "a", "†" … when the paper uses markers
    source: str = ""                 # the paper text it was read from


@dataclass
class Email:
    id: str                          # "E1"
    address: str
    author_id: Optional[str] = None  # who it belongs to; None until linked
    how: str = ""                    # "next to the name", "name match", "only author", …


@dataclass
class Author:
    id: str                          # "A1", in printed order
    name: str
    markers: list[str] = field(default_factory=list)       # as printed after the name
    affiliation_ids: list[str] = field(default_factory=list)
    email_id: Optional[str] = None
    corresponding: bool = False
    source: str = ""


@dataclass
class Check:
    name: str                        # "every author has an affiliation"
    ok: bool
    detail: str = ""                 # what's wrong, in plain words


@dataclass
class Paper:
    title: str = ""
    authors: list[Author] = field(default_factory=list)
    affiliations: list[Affiliation] = field(default_factory=list)
    emails: list[Email] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    footnotes: dict[str, str] = field(default_factory=dict)   # marker -> "These authors contributed equally", …
    trace: list[str] = field(default_factory=list)          # one line per step: what it found

    # ---- lookups
    def affiliation(self, fid: str) -> Optional[Affiliation]:
        return next((f for f in self.affiliations if f.id == fid), None)

    def email_of(self, author: Author) -> Optional[str]:
        e = next((e for e in self.emails if e.id == author.email_id), None)
        return e.address if e else None

    # ---- outputs
    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": [{"id": a.id, "name": a.name, "affiliation_ids": a.affiliation_ids, "email": self.email_of(a),
                         "corresponding": a.corresponding} for a in self.authors],
            "affiliations": [{"id": f.id, "marker": f.marker, "text": f.text} for f in self.affiliations],
            "emails": [{"id": e.id, "address": e.address, "author_id": e.author_id, "how": e.how} for e in self.emails],
            "footnotes": self.footnotes,
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in self.checks],
            "trace": self.trace,
        }

    def as_benchmark(self) -> dict:
        """The shape benchmark/score.py grades."""
        return {"title": self.title, "authors": [
            {"name": a.name, "emails": [self.email_of(a)] if self.email_of(a) else [],
             "affiliations": [self.affiliation(f).text for f in a.affiliation_ids if self.affiliation(f)],
             "corresponding": a.corresponding} for a in self.authors]}
