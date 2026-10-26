"""Extraction service: bytes in, result dict out.

The limits that protect the server live here and in the loaders: a page cap
and an OCR page cap for PDFs, a size cap for LaTeX, zip-bomb checks for Word
files and a pixel cap for images. Nothing is written to disk; the bytes exist
only for the duration of this call.
"""
from __future__ import annotations

from dataclasses import dataclass

from .core import detect
from .core.models import Document
from .errors import UnsupportedFile
from .ingest import ocr
from .ingest.docx import load_docx
from .ingest.latex import load_tex
from .ingest.pdf import load_pdf
from .paper import pipeline as paper_pipeline
from .upi import pipeline as upi_pipeline

__all__ = ["Limits", "UnsupportedFile", "load", "run"]


@dataclass(frozen=True)
class Limits:
    max_pdf_pages: int = 120
    max_ocr_pages: int = 20
    max_tex_bytes: int = 2 * 1024 * 1024


def load(data: bytes, filename: str, limits: Limits = Limits()) -> Document:
    ftype = detect.sniff(data, filename)
    if ftype == "pdf":
        return load_pdf(data, max_pages=limits.max_pdf_pages, max_ocr_pages=limits.max_ocr_pages)
    if ftype == "docx":
        return load_docx(data)
    if ftype == "tex":
        if len(data) > limits.max_tex_bytes:
            raise UnsupportedFile(f"LaTeX files over {limits.max_tex_bytes // 1024} KB aren't accepted. Upload the main .tex file only.")
        return load_tex(data)
    if ftype == "image":
        blocks, size = ocr.ocr_image_bytes(data)
        return Document(source="image", blocks=blocks, pages=1, page_sizes={1: size})
    raise UnsupportedFile("Upload a PDF, Word (.docx), LaTeX (.tex) or image (PNG, JPG, WEBP) file.")


def run(data: bytes, filename: str = "", kind: str = "auto", allow_ai: bool = False, limits: Limits = Limits()) -> dict:
    """`allow_ai` is the person's own choice for this upload; without it no
    text from the file is ever sent to an LLM provider."""
    doc = load(data, filename, limits)
    chosen = kind if kind in ("paper", "upi") else detect.guess_kind(doc)
    guessed = detect.guess_kind(doc) if kind in ("paper", "upi") else chosen
    result = paper_pipeline.run(doc, allow_ai=allow_ai) if chosen == "paper" else upi_pipeline.run(doc)
    out = result.to_dict()
    out["filename"] = filename
    out["kind_chosen_by"] = "you" if kind in ("paper", "upi") else "auto-detect"
    if guessed != chosen:
        other = "a research paper" if guessed == "paper" else "a UPI receipt"
        out["warnings"].insert(0, f"This file looks more like {other}. Switch the document type if the results look wrong.")
    return out
