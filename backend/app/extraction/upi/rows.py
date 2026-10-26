"""Group OCR boxes or PDF lines into visual rows, read left to right."""
from __future__ import annotations

from dataclasses import dataclass

from ..core.models import Block


@dataclass
class Row:
    text: str
    height: float
    y: float
    blocks: list[Block]


def build_rows(blocks: list[Block]) -> list[Row]:
    with_box = [b for b in blocks if b.bbox]
    if not with_box:
        return [Row(text=b.text, height=b.font_size or 10, y=i, blocks=[b]) for i, b in enumerate(blocks)]
    rows: list[list[Block]] = []
    for b in sorted(with_box, key=lambda b: ((b.page or 0), (b.bbox[1] + b.bbox[3]) / 2)):
        cy = (b.bbox[1] + b.bbox[3]) / 2
        if rows:
            last = rows[-1]
            ly0 = min(x.bbox[1] for x in last)
            ly1 = max(x.bbox[3] for x in last)
            if last[0].page == b.page and ly0 <= cy <= ly1:
                last.append(b)
                continue
        rows.append([b])
    out = []
    for r in rows:
        r.sort(key=lambda b: b.bbox[0])
        out.append(Row(
            text="  ".join(b.text for b in r),
            height=max(b.bbox[3] - b.bbox[1] for b in r),
            y=min(b.bbox[1] for b in r),
            blocks=r,
        ))
    return out
