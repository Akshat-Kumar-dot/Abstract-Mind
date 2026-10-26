"""Extraction.

The file is sent as the raw request body (not multipart), read into memory
with a hard limit, processed, and dropped. Multipart uploads would be spooled
to a temporary file on disk past 1 MB; a raw body never is. The result goes
back to the browser only. Saving happens separately, encrypted, through
/documents.
"""

import re
import threading
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from ...extraction.service import Limits, UnsupportedFile, run
from ...security.ratelimit import enforce
from ...settings import Settings
from ..deps import client_ip, settings
from ..errors import log_safely

router = APIRouter(tags=["extract"])

_slots_lock = threading.Lock()
_slots: dict[int, threading.BoundedSemaphore] = {}
WAIT_FOR_SLOT = 25        # seconds a request waits for a free extraction slot


def _slot(n: int) -> threading.BoundedSemaphore:
    with _slots_lock:
        return _slots.setdefault(n, threading.BoundedSemaphore(n))


def clean_filename(raw: str) -> str:
    name = unquote(raw or "")[:400]
    name = re.split(r"[\\/]", name)[-1]                     # no paths
    name = re.sub(r"[\x00-\x1f\x7f<>\"]", "", name).strip()   # no control or markup characters
    return name[:180] or "untitled"


async def read_limited(request: Request, limit: int) -> bytes:
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"File is larger than {limit // (1024 * 1024)} MB.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/extract")
async def extract(request: Request,
                  kind: str = Query("auto", pattern="^(auto|paper|upi)$"),
                  allow_ai: bool = Query(False),
                  x_file_name: str = Header("", max_length=1024),
                  s: Settings = Depends(settings)) -> dict:
    enforce(f"extract:{client_ip(request)}", 40, 600, "uploads")
    data = await read_limited(request, s.max_upload_bytes)
    if not data:
        raise HTTPException(400, "The file is empty.")
    name = clean_filename(x_file_name)
    limits = Limits(max_pdf_pages=s.max_pdf_pages, max_ocr_pages=s.max_ocr_pages, max_tex_bytes=s.max_tex_bytes)
    slot = _slot(s.max_concurrent_extractions)

    def work() -> dict:
        if not slot.acquire(timeout=WAIT_FOR_SLOT):
            raise HTTPException(503, "Abstract Mind is busy reading other files. Try again in a minute.")
        try:
            return run(data, name, kind, allow_ai=allow_ai and s.llm_provider is not None, limits=limits)
        finally:
            slot.release()

    try:
        return await run_in_threadpool(work)
    except (HTTPException, UnsupportedFile) as e:
        if isinstance(e, UnsupportedFile):
            raise HTTPException(415, str(e)) from None
        raise
    except Exception as e:      # never echo file contents back, never log them
        log_safely("Extraction failed", e)
        raise HTTPException(422, "This file could not be read. It may be damaged or in an unusual format.") from None
