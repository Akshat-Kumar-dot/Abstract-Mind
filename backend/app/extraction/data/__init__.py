from __future__ import annotations

from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def load_list(name: str) -> tuple[str, ...]:
    lines = (DATA_DIR / name).read_text(encoding="utf-8").splitlines()
    return tuple(ln.strip() for ln in lines if ln.strip() and not ln.startswith("#"))
