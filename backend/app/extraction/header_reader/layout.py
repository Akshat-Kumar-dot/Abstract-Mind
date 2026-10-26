"""Page text as lines in reading order.

The PDF loader gives one Block per printed line *fragment*, in whatever order
the file stores them (a BMC paper stores its footer before its title). Here
fragments are grouped into rows by their vertical centre, then joined left to
right where they touch, and the lines are sorted top to bottom.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.models import Block, Document

MARKERS_ONLY = re.compile(r"^[\d,\s*†‡§¶#a-z]{1,12}$")


@dataclass
class Line:
    text: str          # plain text, markers removed
    marked: str        # text with superscript markers kept as ^{…}
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    bold: bool = False
    loose: list = field(default_factory=list)   # marker fragments printed inside the line: (x, "^{1}")

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1.0)


def _rows(blocks: list[Block]) -> list[list[Block]]:
    """Fragments whose vertical centres fall within the same printed row."""
    rows: list[list[Block]] = []
    for b in sorted(blocks, key=lambda b: (b.bbox[1] + b.bbox[3]) / 2):
        centre, h = (b.bbox[1] + b.bbox[3]) / 2, b.bbox[3] - b.bbox[1]
        if rows:
            top = min(x.bbox[1] for x in rows[-1])
            bottom = max(x.bbox[3] for x in rows[-1])
            if top - 0.2 * h <= centre <= bottom + 0.2 * h:
                rows[-1].append(b)
                continue
        rows.append([b])
    return rows


def lines_of(doc: Document, page: int) -> list[Line]:
    lines: list[Line] = []
    for row in _rows([b for b in doc.blocks if b.page == page and b.bbox]):
        current = None
        for b in sorted(row, key=lambda b: b.bbox[0]):
            x0, y0, x1, y1 = b.bbox
            touching = current is not None and -1 < x0 - current.x1 < 1.6 * max(current.size, b.font_size)
            small_markers = touching and b.font_size < 0.8 * current.size and MARKERS_ONLY.match(b.text)
            same_size = touching and abs(b.font_size - current.size) < 0.8   # a different size is another column
            if small_markers or same_size:
                if small_markers:                                             # small "1,2" = markers
                    current.marked += "^{" + b.text.replace(" ", "") + "}"
                else:
                    joiner = "" if current.text.endswith("-") else " "
                    current.text = (current.text + joiner + b.text).strip()
                    current.marked = (current.marked + joiner + b.marked).strip()
                current.x1, current.y0, current.y1 = max(current.x1, x1), min(current.y0, y0), max(current.y1, y1)
                continue
            # a small marker printed just left of the text it labels (MDPI: "1   School of …")
            leading = (current is not None and current.text == current.marked and MARKERS_ONLY.match(current.text)
                       and current.size < 0.8 * b.font_size and 0 <= x0 - current.x1 < 2.5 * b.font_size)
            if leading:
                current.marked = "^{" + current.text.replace(" ", "") + "}" + b.marked
                current.text, current.size, current.bold = b.text, b.font_size, b.bold
                current.x1, current.y0, current.y1 = x1, min(current.y0, y0), max(current.y1, y1)
                continue
            current = Line(b.text, b.marked, page, x0, y0, x1, y1, b.font_size, b.bold)
            lines.append(current)
    return lines           # rows top to bottom (by centre), each row left to right


def page_size(doc: Document, page: int) -> tuple[float, float]:
    return doc.page_sizes.get(page, (612.0, 792.0))
