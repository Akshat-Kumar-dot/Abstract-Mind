"""Counts are computed in code from the document itself."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..core.models import Block, Document
from ..core.text import count_words, join_lines
from .zones import Zones

FIG = re.compile(r"^\s*(?:fig\.?|figure)\s*(\d+|[ivxlc]+)\b\s*[:.\-—–|]?", re.I)
TAB = re.compile(r"^\s*table\s*(\d+|[ivxlc]+)\b\s*[:.\-—–|]?", re.I)


@dataclass
class Stats:
    pages: Optional[int]
    words_main: int
    words_with_refs: int
    figures: int
    tables: int
    references: Optional[int]
    references_how: str


def compute(doc: Document, z: Zones) -> Stats:
    main = join_lines([z.abstract or ""] + [b.text for b in z.body])
    refs_text = join_lines(b.text for b in z.references)
    figs = {m.group(1).lower() for b in z.body + z.tail if (m := FIG.match(b.text))}
    tabs = {m.group(1).lower() for b in z.body + z.tail if (m := TAB.match(b.text))}
    n_refs, how = count_references(z.references, {p: s[0] for p, s in doc.page_sizes.items()})
    return Stats(
        pages=doc.pages,
        words_main=count_words(main),
        words_with_refs=count_words(main) + count_words(refs_text),
        figures=len(figs),
        tables=len(tabs),
        references=n_refs,
        references_how=how,
    )


def count_references(refs: list[Block], page_widths: Optional[dict[int, float]] = None) -> tuple[Optional[int], str]:
    if not refs:
        return None, "no references section found"
    bracket = [int(m.group(1)) for b in refs if (m := re.match(r"^\s*\[(\d{1,3})\]", b.text))]
    if len(bracket) >= 3:
        return max(bracket), "numbered [n] entries"
    numbered = [int(m.group(1)) for b in refs if (m := re.match(r"^\s*(\d{1,3})\.\s+\S", b.text))]
    if len(numbered) >= 3 and max(numbered) <= len(refs):
        return max(numbered), "numbered entries"
    if refs[0].bbox is None:
        return len(refs), "one entry per paragraph"
    # Author-year lists: an entry starts at the column's left edge, continuation
    # lines are indented.
    count = 0
    widths = page_widths or {}

    def col(b: Block) -> tuple:
        mid = widths.get(b.page, 612) / 2
        return (b.page, (b.bbox[0] + b.bbox[2]) / 2 >= mid)

    margins: dict[tuple, float] = {}
    for b in refs:
        margins[col(b)] = min(margins.get(col(b), b.bbox[0]), b.bbox[0])
    prev_end = "."
    for b in refs:
        key = col(b)
        at_margin = abs(b.bbox[0] - margins[key]) < 1.5
        if at_margin and (prev_end.endswith(".") or prev_end.endswith(")")) and b.text[:1].isupper():
            count += 1
        prev_end = b.text.rstrip()
    return (count or None), "entries by hanging indent (estimate)"
