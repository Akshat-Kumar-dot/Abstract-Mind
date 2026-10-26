"""OCR for screenshots and scanned pages. Returns one Block per detected text line."""
from __future__ import annotations

import io
import threading
from typing import Optional

from ..core.models import Block
from ..errors import UnsupportedFile

_engine = None
_lock = threading.Lock()


class OCRUnavailable(UnsupportedFile):
    """Fatal for a screenshot; for a PDF only the scanned pages are skipped."""


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError:  # pragma: no cover - depends on install
                raise OCRUnavailable("Screenshots can't be read on this server: OCR is not installed.") from None
            _engine = RapidOCR()
        return _engine


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


MAX_PIXELS = 40_000_000      # refuse decompression bombs before decoding them
MAX_SIDE = 4000              # bigger images are scaled down: OCR gains nothing past this


def ocr_image_bytes(data: bytes, page: Optional[int] = 1, scale: float = 1.0) -> tuple[list[Block], tuple[float, float]]:
    """OCR an image. Coordinates are divided by `scale` so scanned PDF pages come
    back in PDF points. Font size is estimated from line height."""
    import numpy as np
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w * h > MAX_PIXELS:
            raise UnsupportedFile("This image is too large. Upload a screenshot or a smaller scan.")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Image.DecompressionBombError:
        raise UnsupportedFile("This image is too large. Upload a screenshot or a smaller scan.") from None
    except (UnidentifiedImageError, OSError):
        raise UnsupportedFile("This image can't be read. Upload a PNG, JPG or WEBP.") from None
    w, h = img.size
    # Small screenshots read better a little larger; huge ones only cost time.
    up = 1.0
    if max(w, h) < 1000:
        up = 1000 / max(w, h)
    elif max(w, h) > MAX_SIDE:
        up = MAX_SIDE / max(w, h)
    if up != 1.0:
        img = img.resize((max(1, int(w * up)), max(1, int(h * up))))
    result, _ = _get_engine()(np.array(img))
    blocks: list[Block] = []
    for box, text, conf in result or []:
        text = (text or "").strip()
        if not text:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        k = up * scale
        x0, y0, x1, y1 = min(xs) / k, min(ys) / k, max(xs) / k, max(ys) / k
        blocks.append(Block(text=text, marked=text, page=page, bbox=(x0, y0, x1, y1), font_size=round((y1 - y0) * 0.75, 1)))
    return blocks, (w / scale, h / scale)
