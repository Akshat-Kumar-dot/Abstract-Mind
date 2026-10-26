"""Abstract Mind web service.

`create_app()` wires the layers together:

  middleware   body-size limits, same-origin check for writes, security headers
  /api/v1      health, auth, account, extract, documents (see app/api/routes)
  /            the static web app (web/), served with a strict CSP

Run locally with:  uvicorn app.main:app --app-dir backend --port 8765
"""

import logging

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from .api import errors
from .api.routes import account, auth, documents, extract, google, health
from .security.middleware import (BodyLimitMiddleware, ReaderCorsMiddleware, SameOriginMiddleware,
                                  SecurityHeadersMiddleware)
from .settings import WEB_DIR, get_settings

API_PREFIX = "/api/v1"
JSON_LIMIT = 64 * 1024


def _body_limit(path: str) -> int:
    s = get_settings()
    if path == f"{API_PREFIX}/extract":
        return s.max_upload_bytes + 1024
    if path.startswith(f"{API_PREFIX}/documents"):
        return s.max_document_bytes * 4 // 3 + JSON_LIMIT
    return JSON_LIMIT


def create_app() -> FastAPI:
    get_settings()          # fail fast on a bad production configuration
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    app = FastAPI(title="Abstract Mind", docs_url=None, redoc_url=None, openapi_url=None)
    errors.install(app)

    api = APIRouter(prefix=API_PREFIX)
    for module in (health, auth, google, account, extract, documents):
        api.include_router(module.router)
    app.include_router(api)

    if not get_settings().production:
        from .devtools import mount_extension_preview

        mount_extension_preview(app)       # /_dev/extension/: try the popup locally
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

    # Added last = runs first.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(SameOriginMiddleware)
    app.add_middleware(BodyLimitMiddleware, limit_for=_body_limit)
    app.add_middleware(ReaderCorsMiddleware)     # outermost: answers preflights first
    return app


app = create_app()
