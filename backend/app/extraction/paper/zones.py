"""Zone splitting: header, abstract, keywords, body, references. This paper's own
details are only ever read from the header zone."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..core.models import Block, Document
from ..core.text import join_lines
from ..ingest import layout
from .anchors import after_anchor, anchor, heading_like

HEADER_ANCHORS = ("abstract", "keywords", "introduction", "article_info")


@dataclass
class Zones:
    body_size: float
    header: list[Block] = field(default_factory=list)       # row-major order
    footnotes: list[Block] = field(default_factory=list)    # page-1 footnotes, part of the header
    abstract: Optional[str] = None
    abstract_block: Optional[Block] = None
    abstract_inferred: bool = False          # no heading; opening paragraph taken
    keywords: list[str] = field(default_factory=list)
    keywords_block: Optional[Block] = None
    body: list[Block] = field(default_factory=list)          # reading order
    references: list[Block] = field(default_factory=list)
    tail: list[Block] = field(default_factory=list)          # appendix, biographies
    header_found_by: str = "anchor"


def split(doc: Document) -> Zones:
    body_size = layout.body_font_size(doc.blocks)
    z = Zones(body_size=body_size)
    has_layout = bool(doc.page_sizes) and all(b.bbox is not None for b in doc.blocks)
    if has_layout:
        rest = _split_header_layout(doc, z)
    else:
        rest = _split_header_flow(doc, z)
    _abstract_keywords(rest, z)
    _references(rest, z)
    return z


def _split_header_layout(doc: Document, z: Zones) -> list[Block]:
    p1 = [b for b in doc.blocks if b.page == 1]
    p2 = [b for b in doc.blocks if b.page == 2]

    def first_anchor_y(blocks: list[Block]) -> Optional[float]:
        ys = [b.bbox[1] for b in blocks if anchor(b, z.body_size) in HEADER_ANCHORS]
        return min(ys) if ys else None

    header: list[Block] = []
    y = first_anchor_y(p1)
    if y is not None:
        header = [b for b in p1 if b.bbox[3] <= y + 1]
        z.header_found_by = "anchor"
    else:
        y2 = first_anchor_y(p2)
        if y2 is not None:
            # A separate title page: all of page 1, plus page 2 above the abstract.
            header = p1 + [b for b in p2 if b.bbox[3] <= y2 + 1]
            z.header_found_by = "title page"
        else:
            # No headings (Nature, Science, Cell...): the header ends where the
            # first run of prose starts. Author lists are long too, but they are
            # nearly all capitalised words, so they never count as prose.
            start = _prose_start(p1)
            if start is not None:
                header = [b for b in p1 if b.bbox[1] < start - 1]
                z.header_found_by = "first paragraph"
            else:
                limit = doc.page_sizes[1][1] * 0.35
                header = [b for b in p1 if b.bbox[3] <= limit + 1]
                z.header_found_by = "layout fallback"

    header_ids = {id(b) for b in header}
    h1 = doc.page_sizes.get(1, (0, 792))[1]
    footnotes = [b for b in p1 if id(b) not in header_ids and b.bbox[1] > 0.8 * h1 and b.font_size < z.body_size * 0.95]
    z.header = layout.row_major(header)
    z.footnotes = sorted(footnotes, key=lambda b: (b.bbox[1], b.bbox[0]))
    skip = header_ids | {id(b) for b in footnotes}

    rest: list[Block] = []
    for pno in range(1, (doc.pages or 1) + 1):
        page_blocks = [b for b in doc.blocks if b.page == pno and id(b) not in skip]
        rest.extend(layout.reading_order(page_blocks, doc.page_sizes[pno][0]))
    return rest


def is_prose(b: Block) -> bool:
    words = b.text.split()
    if len(words) < 6:
        return False
    lower = sum(1 for w in words if w[:1].islower())
    return lower / len(words) >= 0.35


def _prose_start(blocks: list[Block]) -> Optional[float]:
    """Top of the first block that starts three prose lines in a row."""
    ordered = sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0]))
    for i, b in enumerate(ordered):
        if not is_prose(b):
            continue
        same_col = [n for n in ordered[i + 1:] if abs(n.bbox[0] - b.bbox[0]) < 12 and n.bbox[1] > b.bbox[1]][:2]
        if len(same_col) == 2 and all(is_prose(n) or len(n.text.split()) >= 3 for n in same_col) \
                and same_col[0].bbox[1] - b.bbox[3] < 2 * max(b.font_size, 6):
            return b.bbox[1]
    return None


def _split_header_flow(doc: Document, z: Zones) -> list[Block]:
    """DOCX and OCR'd text without trustworthy positions: document order."""
    idx = next((i for i, b in enumerate(doc.blocks[:120]) if anchor(b, z.body_size) in HEADER_ANCHORS), None)
    if idx is None:
        idx = next((i for i, b in enumerate(doc.blocks[:120]) if len(b.text.split()) >= 25), min(len(doc.blocks), 12))
        z.header_found_by = "layout fallback"
    z.header = doc.blocks[:idx]
    return doc.blocks[idx:]


def _abstract_keywords(rest: list[Block], z: Zones) -> None:
    consumed: set[int] = set()
    for i, b in enumerate(rest[:200]):
        kind = anchor(b, z.body_size)
        if kind == "abstract" and z.abstract is None:
            lines = [after_anchor(b.text)]
            consumed.add(id(b))
            for nb in rest[i + 1:]:
                nk = anchor(nb, z.body_size)
                if nk or (heading_like(nb, z.body_size) and len(nb.text.split()) <= 6) or _is_copyright(nb.text):
                    break
                if nb.page and b.page and nb.page > b.page + 1:
                    break
                lines.append(nb.text)
                consumed.add(id(nb))
                if len(" ".join(lines).split()) > 600:
                    break
            text = join_lines(lines)
            if text:
                z.abstract, z.abstract_block = text, b
        elif kind == "keywords" and not z.keywords:
            lines = [after_anchor(b.text)]
            consumed.add(id(b))
            prev = b
            for nb in rest[i + 1:i + 8]:
                if anchor(nb, z.body_size) or heading_like(nb, z.body_size) and len(nb.text.split()) <= 6:
                    break
                if prev.bbox and nb.bbox and nb.bbox[1] - prev.bbox[3] > 1.2 * max(nb.font_size, 6):
                    break
                if lines[-1].rstrip().endswith(".") and len(" ".join(lines)) > 20:
                    break
                lines.append(nb.text)
                consumed.add(id(nb))
                prev = nb
                if len(" ".join(lines)) > 300:
                    break
            z.keywords = _split_keywords([ln for ln in lines if ln.strip()])
            z.keywords_block = b
        if z.abstract and z.keywords:
            break
    if z.abstract is None and z.header_found_by == "first paragraph" and rest and rest[0].bbox:
        _infer_abstract(rest, z, consumed)
    rest[:] = [b for b in rest if id(b) not in consumed]


def _infer_abstract(rest: list[Block], z: Zones, consumed: set[int]) -> None:
    """No 'Abstract' heading: take the opening paragraph when it is set apart
    from the body text (its own size or column), as Nature's summary is."""
    first = rest[0]
    lines = []
    for b in rest:
        if b.page != first.page or abs(b.font_size - first.font_size) > 0.3 or abs(b.bbox[0] - first.bbox[0]) > 12:
            break
        lines.append(b)
    if len(lines) == len(rest):
        return
    after = rest[len(lines)]
    distinct = abs(first.font_size - z.body_size) >= 0.4 or abs(first.bbox[0] - after.bbox[0]) > 12
    text = join_lines(b.text for b in lines)
    if distinct and 40 <= len(text.split()) <= 450:
        z.abstract, z.abstract_block, z.abstract_inferred = text, first, True
        consumed.update(id(b) for b in lines)


def _split_keywords(lines: list[str]) -> list[str]:
    joined = join_lines(lines)
    if re.search(r"[;,·•]|\s[–—]\s", joined):
        parts = re.split(r"\s*[;,·•]\s*|\s+[–—]\s+", joined)
    elif len(lines) > 1:
        parts = lines          # Elsevier: one keyword per line
    else:
        parts = [joined]
    return [p.strip(" .") for p in parts if p.strip(" .")]


def _is_copyright(t: str) -> bool:
    return bool(re.match(r"^\s*(©|\(c\)|copyright)", t, re.I))


REF_START = re.compile(r"^\s*(?:\[\d{1,3}\]|\d{1,3}\.)\s+\S")
SECTION_WORDS = re.compile(r"^(acknowledge?ments?|author\s+contributions?|competing\s+interests?|conflicts?\s+of\s+interests?|"
                           r"funding|data\s+availability|code\s+availability|additional\s+information|ethics|methods)\b", re.I)


def _section_start(b: Block, body_size: float) -> bool:
    """A heading, or a run-in heading such as 'Acknowledgements We thank...'."""
    return bool(b.lead_bold or anchor(b, body_size) or heading_like(b, body_size) or SECTION_WORDS.match(b.text))


def _references_without_heading(rest: list[Block], z: Zones) -> None:
    """Nature-style lists: no heading, just numbered entries in smaller type,
    sometimes in more than one run (after the main text and after Methods)."""
    small = [b for b in rest if b.font_size and b.font_size <= z.body_size - 0.75]
    if sum(1 for b in small if REF_START.match(b.text)) < 5:
        z.body = rest
        return
    refs: list[Block] = []
    run_size: Optional[float] = None
    for b in rest:
        if run_size is None:
            if b in small and REF_START.match(b.text):
                run_size = b.font_size
                refs.append(b)
        elif abs(b.font_size - run_size) <= 0.3 and not _section_start(b, z.body_size):
            refs.append(b)
        else:
            run_size = None
    ids = {id(b) for b in refs}
    z.references = refs
    z.body = [b for b in rest if id(b) not in ids]


def _references(rest: list[Block], z: Zones) -> None:
    ref_idx = None
    for i, b in enumerate(rest):
        if anchor(b, z.body_size) == "references":
            ref_idx = i          # keep the last one: that is the list at the end
    if ref_idx is None:
        _references_without_heading(rest, z)
        return
    z.body = rest[:ref_idx]
    end = len(rest)
    for j in range(ref_idx + 1, len(rest)):
        if anchor(rest[j], z.body_size) in ("appendix", "biography"):
            end = j
            break
    z.references = rest[ref_idx + 1:end]
    z.tail = rest[end:]
