"""Checks on extracted UPI values. Each failed check lowers confidence."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))
UPI_LAUNCH_YEAR = 2016


def utr_ok(utr: Optional[str], text: str) -> int:
    if not utr:
        return 0
    failed = 0 if re.fullmatch(r"\d{12}", utr) else 1
    if utr not in re.sub(r"(?<=\d)\s(?=\d)", "", text):
        failed += 1
    return failed


def amount_ok(value: Optional[Decimal]) -> int:
    if value is None:
        return 0
    return 0 if Decimal("0") < value < Decimal("10000000") else 1


def date_ok(dt: Optional[datetime]) -> int:
    if dt is None:
        return 0
    now = datetime.now(IST)
    return 0 if dt.year >= UPI_LAUNCH_YEAR and dt <= now + timedelta(days=1) else 1
