"""Application settings, read from environment variables.

A local `.env` file at the repository root is read too, so the same keys work
on a laptop and on Render. Every setting has a safe default for local use.
With APP_ENV=production the session cookie is Secure (and __Host- prefixed),
HSTS is sent, and APP_SECRET must be set.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"

_DEV_SECRET = b"abstract-mind-development-secret-not-for-production"


def _load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _int(name: str, default: int) -> int:
    return int(float(os.getenv(name, str(default))))


@dataclass(frozen=True)
class Settings:
    env: str
    database_url: Optional[str]      # Postgres when set; otherwise SQLite at db_path
    db_path: Path
    app_secret: bytes
    public_origin: Optional[str]
    session_days: int
    # uploads and extraction
    max_upload_bytes: int
    max_pdf_pages: int
    max_ocr_pages: int
    max_tex_bytes: int
    max_concurrent_extractions: int
    # encrypted library
    max_document_bytes: int
    max_documents_per_user: int
    # optional LLM help (off unless the user ticks it for an upload)
    llm_provider: Optional[str]
    gemini_api_key: Optional[str]
    gemini_model: str
    groq_api_key: Optional[str]
    groq_model: str
    llm_timeout: float
    # "Continue with Google" (off unless both are set)
    google_client_id: Optional[str]
    google_client_secret: Optional[str]

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def production(self) -> bool:
        return self.env == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.production

    @property
    def cookie_name(self) -> str:
        # __Host- cookies must be Secure, host-only and Path=/; browsers enforce it.
        return "__Host-am_session" if self.cookie_secure else "am_session"


def _llm_provider() -> Optional[str]:
    choice = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    has_gemini, has_groq = bool(os.getenv("GEMINI_API_KEY")), bool(os.getenv("GROQ_API_KEY"))
    if choice == "none":
        return None
    if choice == "gemini":
        return "gemini" if has_gemini else None
    if choice == "groq":
        return "groq" if has_groq else None
    return "gemini" if has_gemini else "groq" if has_groq else None


def get_settings() -> Settings:
    """Read on every call: cheap, and lets tests change the environment."""
    env = os.getenv("APP_ENV", "development").strip().lower()
    secret = os.getenv("APP_SECRET", "").encode()
    if not secret:
        if env == "production":
            raise RuntimeError("APP_SECRET must be set when APP_ENV=production.")
        secret = _DEV_SECRET
    origin = os.getenv("PUBLIC_ORIGIN", "").strip().rstrip("/") or None
    return Settings(
        env=env,
        database_url=os.getenv("DATABASE_URL", "").strip() or None,
        db_path=Path(os.getenv("DB_PATH") or ROOT / "data" / "abstract_mind.db"),
        app_secret=secret,
        public_origin=origin,
        session_days=_int("SESSION_DAYS", 30),
        max_upload_bytes=int(float(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024),
        max_pdf_pages=_int("MAX_PDF_PAGES", 120),
        max_ocr_pages=_int("MAX_OCR_PAGES", 20),
        max_tex_bytes=_int("MAX_TEX_KB", 2048) * 1024,
        max_concurrent_extractions=max(1, _int("MAX_CONCURRENT_EXTRACTIONS", 2)),
        max_document_bytes=_int("MAX_DOCUMENT_KB", 4096) * 1024,
        max_documents_per_user=_int("MAX_DOCUMENTS_PER_USER", 5000),
        llm_provider=_llm_provider(),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        llm_timeout=float(os.getenv("LLM_TIMEOUT", "30")),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip() or None,
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip() or None,
    )
