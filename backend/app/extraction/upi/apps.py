"""App templates and app detection."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..core.detect import VPA

TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def templates() -> dict[str, dict]:
    out = {}
    for path in sorted(TEMPLATE_DIR.glob("*.yaml")):
        out[path.stem] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return out


def detect(text: str) -> tuple[str, dict]:
    """Best-matching template. UPI IDs are removed first, so paying a
    merchant at name@paytm from Google Pay is not read as Paytm."""
    t = VPA.sub(" ", text).lower()
    best, best_hits = "generic", 0
    for key, tpl in templates().items():
        hits = sum(1 for kw in tpl.get("detect", []) if kw in t)
        if hits > best_hits:
            best, best_hits = key, hits
    return best, templates()[best]
