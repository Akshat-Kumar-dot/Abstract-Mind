import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from tests.make_fixtures import OUT, build  # noqa: E402

NAMES = ["ieee.pdf", "lncs.pdf", "nature.pdf", "manuscript.docx", "acm.tex", "ieee.tex", "elsarticle.tex",
         "phonepe.png", "gpay.png", "paytm.pdf"]


@pytest.fixture(scope="session")
def fixtures() -> Path:
    if not all((OUT / n).exists() for n in NAMES):
        build(OUT)
    return OUT


# Tests run on SQLite (a fresh file per test). To run them on Postgres too, set
# TEST_DATABASE_URL to a database that may be emptied: every table is cleared
# before each test. DATABASE_URL itself is never used here, so a production URL
# in .env can't be touched by a test run.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Every test gets an empty database, fresh rate limits and development
    settings."""
    from app.db import database
    from app.security.ratelimit import limiter

    for key in ("APP_ENV", "APP_SECRET", "PUBLIC_ORIGIN", "MAX_UPLOAD_MB", "MAX_DOCUMENTS_PER_USER", "MAX_DOCUMENT_KB",
                "MAX_PDF_PAGES", "MAX_TEX_KB", "GEMINI_API_KEY", "GROQ_API_KEY", "GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_SECRET", "DATABASE_URL", "READER_ALLOWED_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    if TEST_DATABASE_URL:
        monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
        with database.connect() as con:
            con.execute("TRUNCATE users, sessions, documents RESTART IDENTITY CASCADE")
    limiter.reset()
    yield
    limiter.reset()


def pytest_sessionfinish(session, exitstatus):
    from app.db import database

    database.close_pools()
