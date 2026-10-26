"""Confidence: each field starts from how reliable its source is, loses 70% per
failed check, and gains 0.1 when two sources agree."""
from __future__ import annotations

from typing import Any, Optional

from .models import Evidence, Field

BASE = {
    "tex": 0.98,
    "template": 0.95,
    "count": 0.95,
    "rule": 0.85,
    "layout": 0.85,
    "generic": 0.80,
    "suggested": 0.50,
}
VERIFIED = 0.85
CHECK = 0.60


def score(source: str, failed: int = 0, base: Optional[float] = None) -> float:
    c = BASE.get(source, 0.7) if base is None else base
    c *= 0.3 ** failed
    return round(c, 2)


def is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def status_for(value: Any, confidence: float) -> str:
    if is_empty(value):
        return "missing"
    if confidence >= VERIFIED:
        return "verified"
    if confidence >= CHECK:
        return "check"
    return "needs_review"


def make(
    key: str,
    label: str,
    value: Any,
    source: str = "rule",
    *,
    failed: int = 0,
    base: Optional[float] = None,
    evidence: Optional[Evidence] = None,
    note: Optional[str] = None,
    long: bool = False,
) -> Field:
    conf = 0.0 if is_empty(value) else score(source, failed, base)
    return Field(
        key=key,
        label=label,
        value=value,
        source=source if not is_empty(value) else "none",
        confidence=conf,
        status=status_for(value, conf),
        evidence=evidence,
        note=note,
        long=long,
    )
