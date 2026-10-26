"""Layout clean-up and reading order for blocks that have positions."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from ..core.models import Block, Document

PAGE_NUMBER = re.compile(r"^\s*(?:page\s*)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?\s*$", re.I)


def clean(doc: Document) -> None:
    """Drop running headers/footers, page numbers and review line numbers."""
    if not doc.page_sizes:
        return
    n_pages = doc.pages or 1

    def margin(b: Block) -> bool:
        _, h = doc.page_sizes[b.page]
        return b.bbox[1] < 0.09 * h or b.bbox[3] > 0.91 * h

    def sig(t: str) -> str:
        return re.sub(r"\d+", "#", t.strip().lower())

    repeated: set[str] = set()
    if n_pages >= 3:
        pages_by_sig: dict[str, set[int]] = defaultdict(set)
        for b in doc.blocks:
            if b.bbox and margin(b):
                pages_by_sig[sig(b.text)].add(b.page)
        need = max(3, n_pages // 2)
        repeated = {s for s, pages in pages_by_sig.items() if len(pages) >= need}

    kept = []
    for b in doc.blocks:
        if b.bbox is None:
            kept.append(b)
            continue
        w, _ = doc.page_sizes[b.page]
        if margin(b) and (sig(b.text) in repeated or PAGE_NUMBER.match(b.text)):
            continue
        if re.fullmatch(r"\d{1,4}", b.text.strip()) and (b.bbox[2] < 0.12 * w or b.bbox[0] > 0.88 * w):
            continue  # line numbers in the margin of a review manuscript
        kept.append(b)
    doc.blocks = kept


def body_font_size(blocks: list[Block]) -> float:
    sizes: Counter = Counter()
    for b in blocks:
        if b.font_size:
            sizes[round(b.font_size * 2) / 2] += len(b.text)
    return sizes.most_common(1)[0][0] if sizes else 10.0


def row_major(blocks: list[Block], tol: float = 3.0) -> list[Block]:
    """Top-to-bottom rows, left-to-right inside a row. Keeps the order of
    side-by-side author blocks."""
    rows: list[list[Block]] = []
    for b in sorted(blocks, key=lambda b: (b.page or 0, b.bbox[1] if b.bbox else 0)):
        if rows and b.bbox and rows[-1][0].bbox and rows[-1][0].page == b.page and abs(rows[-1][0].bbox[1] - b.bbox[1]) <= tol:
            rows[-1].append(b)
        else:
            rows.append([b])
    out = []
    for r in rows:
        out.extend(sorted(r, key=lambda b: b.bbox[0] if b.bbox else 0))
    return out


def reading_order(blocks: list[Block], page_width: float) -> list[Block]:
    """Order one page's blocks. Two-column bands are read left column first,
    full-width blocks (titles, wide figures) split the bands."""
    if not blocks or blocks[0].bbox is None:
        return blocks
    mid = page_width / 2

    def spanning(b: Block) -> bool:
        return b.bbox[0] < mid - 0.04 * page_width and b.bbox[2] > mid + 0.04 * page_width

    def center(b: Block) -> float:
        return (b.bbox[0] + b.bbox[2]) / 2

    left = [b for b in blocks if not spanning(b) and center(b) < mid]
    right = [b for b in blocks if not spanning(b) and center(b) >= mid]
    if not (_is_column(left) and _is_column(right)):
        return sorted(blocks, key=lambda b: (round(b.bbox[1]), b.bbox[0]))

    out: list[Block] = []
    band: list[Block] = []
    for b in sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0])):
        if spanning(b):
            out.extend(_flush(band, mid))
            band = []
            out.append(b)
        else:
            band.append(b)
    out.extend(_flush(band, mid))
    return out


def _is_column(blocks: list[Block]) -> bool:
    if len(blocks) < 5:
        return False
    xs = sorted(b.bbox[0] for b in blocks)
    median = xs[len(xs) // 2]
    aligned = sum(1 for x in xs if abs(x - median) < 15)
    return aligned >= 0.5 * len(xs)


def _flush(band: list[Block], mid: float) -> list[Block]:
    left = sorted((b for b in band if (b.bbox[0] + b.bbox[2]) / 2 < mid), key=lambda b: (b.bbox[1], b.bbox[0]))
    right = sorted((b for b in band if (b.bbox[0] + b.bbox[2]) / 2 >= mid), key=lambda b: (b.bbox[1], b.bbox[0]))
    return left + right
