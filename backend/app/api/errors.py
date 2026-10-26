"""Error responses. Validation errors name the fields that were wrong but never
echo the submitted values (which could be a key or document text), and
unexpected errors are logged by type and code location only."""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("abstract_mind")


def log_safely(message: str, exc: BaseException) -> None:
    """Exception type plus file:line frames. The exception's own message is
    left out: parsers often quote the input that broke them."""
    frames = traceback.extract_tb(exc.__traceback__)[-6:]
    where = " <- ".join(f"{f.filename.rsplit('/', 1)[-1].rsplit(chr(92), 1)[-1]}:{f.lineno}" for f in reversed(frames))
    log.error("%s: %s at %s", message, type(exc).__name__, where)


def install(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError):
        fields = sorted({".".join(str(p) for p in e.get("loc", ())[1:]) or "body" for e in exc.errors()})
        return JSONResponse({"detail": "Some fields are missing or invalid.", "fields": fields}, status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        log_safely(f"Unhandled error on {request.method} {request.url.path}", exc)
        return JSONResponse({"detail": "Something went wrong on our side."}, status_code=500)
