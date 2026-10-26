"""Word (.docx) to Blocks. No page positions, so blocks keep document order and
carry the style name and font size instead."""
from __future__ import annotations

import io
import re
import zipfile
from typing import Iterator, Optional

from docx import Document as open_docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from ..core.models import Block, Document
from ..core.text import unicode_sup_to_marked
from ..errors import UnsupportedFile


MAX_ENTRIES = 3000
MAX_UNPACKED = 150 * 1024 * 1024     # a .docx is a zip: refuse zip bombs before unpacking


def _check_archive(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
    except zipfile.BadZipFile:
        raise UnsupportedFile("This Word file is damaged and can't be opened.") from None
    if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNPACKED:
        raise UnsupportedFile("This Word file is too large once unpacked. Save it again without embedded media and retry.")


def load_docx(data: bytes) -> Document:
    _check_archive(data)
    try:
        d = open_docx(io.BytesIO(data))
    except Exception:
        raise UnsupportedFile("This Word file can't be opened. Save it as .docx from Word and try again.") from None
    default_size = _default_size(d) or 11.0
    doc = Document(source="docx", blocks=[], pages=_page_count(data))
    # Holding the elements keeps lxml handing back the same object for the same
    # node, so merged table cells (which repeat a paragraph) are skipped.
    seen: set = set()
    for para in _paragraphs(d):
        if para._p in seen:
            continue
        seen.add(para._p)
        doc.blocks.extend(_para_blocks(para, default_size))
    return doc


def _paragraphs(d) -> Iterator[Paragraph]:
    for child in d.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, d)
        elif child.tag == qn("w:tbl"):
            for row in Table(child, d).rows:
                for cell in row.cells:
                    yield from cell.paragraphs


def _para_blocks(para: Paragraph, default_size: float) -> list[Block]:
    style = para.style.name if para.style is not None else None
    style_size = _style_size(para.style) or default_size
    style_bold = _style_bold(para.style)
    lines = [{"plain": [], "marked": [], "sizes": {}, "bold": 0, "chars": 0, "lead": [], "plain_seen": False}]
    for run in para.runs:
        size = run.font.size.pt if run.font.size is not None else style_size
        bold = run.bold if run.bold is not None else style_bold
        sup = bool(run.font.superscript)
        parts = run.text.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                lines.append({"plain": [], "marked": [], "sizes": {}, "bold": 0, "chars": 0, "lead": [], "plain_seen": False})
            cur = lines[-1]
            if sup and part.strip():
                cur["marked"].append("^{" + part.strip() + "}")
                continue
            cur["plain"].append(part)
            cur["marked"].append(part)
            n = len(part.strip())
            cur["sizes"][size] = cur["sizes"].get(size, 0) + n
            cur["chars"] += n
            if bold and n:
                cur["bold"] += n
                if not cur["plain_seen"]:
                    cur["lead"].append(part)
            elif n:
                cur["plain_seen"] = True
    blocks = []
    for ln in lines:
        text = " ".join("".join(ln["plain"]).split())
        if not text:
            continue
        marked = unicode_sup_to_marked(" ".join("".join(ln["marked"]).split()))
        text = " ".join(re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", "", text).split())
        size = max(ln["sizes"], key=ln["sizes"].get) if ln["sizes"] else style_size
        lead = " ".join("".join(ln["lead"]).split()) if ln["lead"] and ln["plain_seen"] else None
        blocks.append(Block(text=text, marked=marked, font_size=float(size), bold=ln["chars"] > 0 and ln["bold"] / ln["chars"] > 0.6,
                            style=style, lead_bold=lead or None))
    return blocks


def _style_size(style) -> Optional[float]:
    while style is not None:
        if style.font is not None and style.font.size is not None:
            return style.font.size.pt
        style = style.base_style
    return None


def _style_bold(style) -> bool:
    while style is not None:
        if style.font is not None and style.font.bold is not None:
            return bool(style.font.bold)
        style = style.base_style
    return False


def _default_size(d) -> Optional[float]:
    sz = d.styles.element.find(qn("w:docDefaults") + "/" + qn("w:rPrDefault") + "/" + qn("w:rPr") + "/" + qn("w:sz"))
    if sz is not None and sz.get(qn("w:val")):
        return int(sz.get(qn("w:val"))) / 2
    return None


def _page_count(data: bytes) -> Optional[int]:
    """Word stores the page count from its last save in docProps/app.xml."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("docProps/app.xml").decode("utf-8", "replace")
    except (KeyError, zipfile.BadZipFile):
        return None
    m = re.search(r"<Pages>(\d+)</Pages>", xml)
    return int(m.group(1)) if m else None
