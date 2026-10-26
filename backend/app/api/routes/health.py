
from fastapi import APIRouter, Depends

from ...db import database
from ...extraction.ingest import ocr
from ...settings import Settings
from ..deps import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(s: Settings = Depends(settings)) -> dict:
    return {
        "ok": True,
        "ai_provider": s.llm_provider,
        "ocr": ocr.available(),
        "max_upload_mb": s.max_upload_bytes // (1024 * 1024),
        "google": s.google_enabled,
        "database": database.backend(),
    }
