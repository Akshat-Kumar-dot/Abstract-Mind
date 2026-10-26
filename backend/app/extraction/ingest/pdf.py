"""PDF to Blocks with PyMuPDF. One Block per text line, keeping font size, bold,
position and superscript markers. Pages without a text layer go through OCR."""
from __future__ import annotations

import re

import fitz  # PyMuPDF

from ..core.models import Block, Document
from ..core.text import unicode_sup_to_marked
from ..errors import UnsupportedFile
from . import ocr

SUPERSCRIPT_FLAG = 1
BOLD_FLAG = 16
BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi", re.I)
OCR_DPI = 200
MAX_RENDER_PIXELS = 25_000_000      # a page declared enormous must not exhaust memory


def load_pdf(data: bytes, max_pages: int = 120, max_ocr_pages: int = 20) -> Document:
    try:
        pdf = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise UnsupportedFile("This PDF is damaged and can't be opened.") from None
    if pdf.needs_pass:
        raise UnsupportedFile("This PDF is password-protected. Remove the password and upload it again.")
    if pdf.page_count > max_pages:
        raise UnsupportedFile(f"This PDF has {pdf.page_count} pages; the limit is {max_pages}. Upload the manuscript without supplements.")
    doc = Document(source="pdf", blocks=[], pages=pdf.page_count)
    scanned = skipped = 0
    for pno, page in enumerate(pdf, start=1):
        doc.page_sizes[pno] = (page.rect.width, page.rect.height)
        page_blocks: list[Block] = []
        info = page.get_text("dict")
        for b in info["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                dx, dy = line["dir"]
                if dx < 0.9 or abs(dy) > 0.1:
                    continue  # rotated text, e.g. the arXiv stamp in the margin
                page_blocks.extend(_line_blocks(line, pno))
        needs_ocr = sum(len(x.text) for x in page_blocks) < 50 and page.get_images()
        if needs_ocr and scanned >= max_ocr_pages:
            skipped += 1                    # OCR is slow; past the cap, scanned pages are skipped
        elif needs_ocr:
            zoom = OCR_DPI / 72
            area = page.rect.width * page.rect.height * zoom * zoom
            if area > MAX_RENDER_PIXELS:
                zoom *= (MAX_RENDER_PIXELS / area) ** 0.5
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            try:
                page_blocks, _ = ocr.ocr_image_bytes(pix.tobytes("png"), page=pno, scale=zoom)
                scanned += 1
            except ocr.OCRUnavailable:
                doc.warnings.append(f"Page {pno} is a scanned image and OCR is not available.")
        doc.blocks.extend(page_blocks)
        for ln in page.get_links():
            uri = ln.get("uri")
            if uri:
                r = ln["from"]
                doc.links.append({"page": pno, "uri": uri, "rect": (r.x0, r.y0, r.x1, r.y1)})
    if scanned:
        doc.source = "ocr" if scanned == pdf.page_count else "pdf"
        doc.warnings.append(f"{scanned} page(s) were scanned images and were read with OCR; check the results closely.")
    if skipped:
        doc.warnings.append(f"{skipped} more scanned page(s) were skipped: only the first {max_ocr_pages} are read with OCR.")
    return doc


def _line_blocks(line: dict, pno: int) -> list[Block]:
    spans = [s for s in line["spans"] if s["text"]]
    if not spans:
        return []
    ref = max(spans, key=lambda s: s["size"])
    base_y, base_size = ref["origin"][1], ref["size"]

    # A wide horizontal gap means two separate things share a baseline
    # (e.g. three IEEE author blocks side by side): split them.
    segments: list[list[dict]] = [[]]
    prev_x1 = None
    for s in spans:
        if prev_x1 is not None and s["bbox"][0] - prev_x1 > 2.5 * max(s["size"], 4):
            segments.append([])
        segments[-1].append(s)
        prev_x1 = s["bbox"][2]

    out = []
    for seg in segments:
        plain, marked = [], []
        size_chars: dict[float, int] = {}
        bold_chars = total_chars = 0
        lead_bold: list[str] = []      # bold spans that open the line
        plain_seen = False
        x0 = y0 = float("inf")
        x1 = y1 = float("-inf")
        prev_end = None
        for s in seg:
            t = s["text"]
            raised = s["origin"][1] < base_y - 0.15 * base_size
            is_sup = bool(s["flags"] & SUPERSCRIPT_FLAG) and s["size"] < base_size * 0.95 or (s["size"] < 0.8 * base_size and raised)
            gap_space = prev_end is not None and s["bbox"][0] - prev_end > 0.2 * s["size"]
            if is_sup and t.strip():
                marked.append("^{" + t.strip() + "}")
            else:
                if gap_space and plain and not plain[-1].endswith(" ") and not t.startswith(" "):
                    plain.append(" ")
                    marked.append(" ")
                plain.append(t)
                marked.append(t)
                n = len(t.strip())
                if n:
                    size_chars[round(s["size"] * 2) / 2] = size_chars.get(round(s["size"] * 2) / 2, 0) + n
                    total_chars += n
                    if s["flags"] & BOLD_FLAG or BOLD_FONT.search(s.get("font", "")):
                        bold_chars += n
                        if not plain_seen:
                            lead_bold.append(t)
                    else:
                        plain_seen = True
            prev_end = s["bbox"][2]
            x0, y0 = min(x0, s["bbox"][0]), min(y0, s["bbox"][1])
            x1, y1 = max(x1, s["bbox"][2]), max(y1, s["bbox"][3])
        text = " ".join("".join(plain).split())
        if not text:
            continue
        m = unicode_sup_to_marked(" ".join("".join(marked).split()))
        text = " ".join(re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", "", text).split())
        size = max(size_chars, key=size_chars.get) if size_chars else base_size
        lb = " ".join("".join(lead_bold).split()) if lead_bold and plain_seen else None
        out.append(Block(text=text, marked=m, page=pno, bbox=(x0, y0, x1, y1), font_size=size,
                         bold=total_chars > 0 and bold_chars / total_chars > 0.6, lead_bold=lb or None))
    return out
