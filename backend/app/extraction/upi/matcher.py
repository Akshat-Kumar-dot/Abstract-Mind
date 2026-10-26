"""Label-anchored rules: find a label, then read the value on the same row or
the next rows. Plus format rules for amounts, dates, status and bank."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterator, Optional

from dateutil import parser as dateparser

from ..data import load_list
from .rows import Row
from .validators import IST

VPA_RE = re.compile(r"[A-Za-z0-9.\-_]{2,256}@[A-Za-z]{2,64}\b(?!\.)")
UTR_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
PHONE_RE = re.compile(r"(?:\+91[\s-]?)?(?<!\d)[6-9]\d{9}(?!\d)")
MASK_RE = re.compile(r"[xX•*·●∙.]{2,}\s*(\d{4})\b")
BANK_DASH_RE = re.compile(r"bank\s*[-–]\s*(\d{4})\b", re.I)
AMOUNT_PREFIX = re.compile(r"(?:₹|rs\.?|inr|¥|￥)\s*([\d,]+(?:\.\d{1,2})?)", re.I)
MONTHS = r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
DATE_RES = [
    re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:" + MONTHS + r")[a-z]*\.?,?\s+\d{2,4}\b", re.I),
    re.compile(r"\b(?:" + MONTHS + r")[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b", re.I),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
]
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?\s?m\.?)?", re.I)
STATUS = [
    ("Failed", re.compile(r"\bfailed\b|\bdeclined\b|\bunsuccessful\b", re.I)),
    ("Pending", re.compile(r"\bpending\b|\bprocessing\b|\bin\s+progress\b|\bawaiting\b", re.I)),
    ("Refunded", re.compile(r"\brefunded\b|\breversed\b", re.I)),
    ("Successful", re.compile(r"\bsuccessful(?:ly)?\b|\bsuccess\b|\bcompleted\b|\bmoney\s+sent\b|\bpayment\s+received\b|\bpaid\b(?!\s+(?:to|from|by|via)\b)", re.I)),
]
BARE_AMOUNT = re.compile(r"[₹¥￥%?]?\s*\b\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?\b|\b\d+\.\d{2}\b")
AMOUNT_BOX = re.compile(r"([₹¥￥%?]|rs\.?|inr)?\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", re.I)
ROW_AMOUNT = re.compile(r"(?<![\w.,])([₹¥￥%?])?\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+\.\d{2})(?![\w,])")
LABEL_WORDS = re.compile(r"(?i)\b(transaction|txn|id|ref|reference|details|powered|upi|utr|order|amount|debited|credited|balance)\b")


def _bank_pattern() -> re.Pattern:
    names = sorted(load_list("banks.txt"), key=len, reverse=True)
    # OCR often drops spaces ("StateBankofIndia"), so spaces are optional
    alts = "|".join(r"\s*".join(map(re.escape, n.split())) for n in names)
    return re.compile(r"(?i)(?<![A-Za-z])(" + alts + r")(?![A-Za-z])")


BANK_RE = _bank_pattern()
PARTY_LABELS = ["paid to", "sent to", "to", "from", "debited from", "paid from", "paid by", "payee", "payer", "beneficiary"]


@dataclass
class Hit:
    value: object
    row: Optional[int]
    how: str          # "template", "generic", "format"
    note: Optional[str] = None
    failed: int = 0


def _label_re(label: str) -> re.Pattern:
    if len(label) <= 4:
        return re.compile(r"^\s*" + re.escape(label) + r"(?![A-Za-z])", re.I)
    return re.compile(r"(?<![A-Za-z])" + re.escape(label) + r"(?![A-Za-z])", re.I)


def find_labels(rows: list[Row], labels: list[str]) -> Iterator[tuple[int, str]]:
    for label in sorted(labels, key=len, reverse=True):
        rx = _label_re(label)
        for i, r in enumerate(rows):
            m = rx.search(r.text)
            if m:
                yield i, r.text[m.end():].lstrip(" :-–#.")


def labelled(rows: list[Row], labels: list[str], pattern: re.Pattern, how: str, join_digits: bool = False) -> Optional[Hit]:
    for i, after in find_labels(rows, labels):
        candidates = [(i, after)] + [(j, rows[j].text) for j in (i + 1, i + 2) if j < len(rows)]
        for j, seg in candidates:
            s = re.sub(r"(?<=\d)\s(?=\d)", "", seg) if join_digits else seg
            m = pattern.search(s)
            if m:
                return Hit(m.group(1) if m.groups() else m.group(0), j, how)
    return None


def utr(rows: list[Row], labels: list[str], how: str) -> Optional[Hit]:
    hit = labelled(rows, labels, UTR_RE, how, join_digits=True)
    if hit:
        return hit
    if how == "generic":
        found = [(i, m.group(0)) for i, r in enumerate(rows) for m in UTR_RE.finditer(re.sub(r"(?<=\d)\s(?=\d)", "", r.text))
                 if not PHONE_RE.fullmatch(m.group(0))]
        if len(found) == 1:
            return Hit(found[0][1], found[0][0], "generic", note="Only 12-digit number on the receipt; no UTR label found")
    return None


def _clean_party(seg: str) -> str:
    s = VPA_RE.sub(" ", seg)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = AMOUNT_PREFIX.sub(" ", s)
    s = BARE_AMOUNT.sub(" ", s)
    s = re.sub(r"[₹¥￥%?]\s*\d[\d,]*(?:\.\d{1,2})?", " ", s)   # "?85": an amount whose ₹ was misread
    s = PHONE_RE.sub(" ", s)
    s = MASK_RE.sub(" ", s)
    s = BANK_DASH_RE.sub(" ", s)
    s = BANK_RE.sub(" ", s)
    s = re.sub(r"(?i)\b(upi\s*id|vpa|banking\s+name|bank\s*a/?c|a/?c\s*no\.?|mobile|phone)\b\s*:?", " ", s)
    s = re.sub(r"[()\[\]|:]", " ", s)
    return " ".join(s.split()).strip(" -,")


def _is_label(seg: str) -> bool:
    low = seg.strip().lower()
    return any(re.match(r"^" + re.escape(lab) + r"(?![a-z])", low) for lab in PARTY_LABELS)


def party(rows: list[Row], labels: list[str], how: str) -> tuple[Optional[Hit], Optional[Hit]]:
    """(name, upi id) after a party label such as 'Paid to' or 'From'.
    Receipts often repeat a label ('To ANJALI' at the top, 'To:' + UPI ID
    lower down), so later hits fill in whatever the first one lacked."""
    name = vpa = None
    for i, after in find_labels(rows, labels):
        segs = [(i, after)] + [(j, rows[j].text) for j in (i + 1, i + 2) if j < len(rows)]
        for k, (j, seg) in enumerate(segs):
            if k > 0 and _is_label(seg):
                break
            v = VPA_RE.search(seg)
            if v and vpa is None:
                vpa = Hit(v.group(0), j, how)
            cand = _clean_party(seg)
            if name is None and len(re.sub(r"[^A-Za-z]", "", cand)) >= 3 and not any(rx.search(cand) for _, rx in STATUS) \
                    and not re.search(r"\d{3,}", cand) and not LABEL_WORDS.search(cand):
                squashed = re.fullmatch(r"[A-Z]{12,}", cand) is not None
                name = Hit(cand, j, how, note="OCR may have dropped the spaces in this name" if squashed else None,
                           failed=1 if squashed else 0)
            if name and vpa:
                break
        if name and vpa:
            break
    return name, vpa


def _to_decimal(s: str) -> Optional[Decimal]:
    try:
        return Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None


def amount(rows: list[Row]) -> Optional[Hit]:
    """Collect amounts: text after ₹/Rs/INR, and OCR boxes holding only a number
    (OCR often drops the ₹ sign). Prefer a ₹-prefixed value, then one printed
    more than once, then the largest type; fix common misreads of ₹."""
    tallest = max((r.height for r in rows), default=0)
    cands = []   # (value, raw, symbol, height, row)
    for i, r in enumerate(rows):
        seen = set()
        for m in AMOUNT_PREFIX.finditer(r.text):
            v = _to_decimal(m.group(1))
            if v is not None:
                cands.append((v, m.group(1), "₹", r.height, i))
                seen.add(m.group(1))
        # "1,250" or "349.00" anywhere in the row (OCR may merge it into a name box)
        for m in ROW_AMOUNT.finditer(r.text):
            v = _to_decimal(m.group(2))
            if v is not None and m.group(2) not in seen:
                cands.append((v, m.group(2), m.group(1), r.height, i))
                seen.add(m.group(2))
        # A box holding only a plain number counts when it is the big headline
        for b in r.blocks:
            m = AMOUNT_BOX.fullmatch(b.text.strip())
            if not m or m.group(2) in seen:
                continue
            sym, raw = m.group(1), m.group(2)
            height = (b.bbox[3] - b.bbox[1]) if b.bbox else r.height
            if sym is None and (len(raw) >= 5 or height < tallest * 0.9):
                continue   # IDs, years and small plain numbers are not amounts
            v = _to_decimal(raw)
            if v is not None:
                cands.append((v, raw, sym, height, i))
    if not cands:
        return None
    counts: dict = {}
    for c in cands:
        counts[c[0]] = counts.get(c[0], 0) + 1

    def strength(c) -> float:
        rupee = c[2] is not None and c[2] not in ("%", "?")
        return rupee * 100 + (counts[c[0]] - 1) * 40 + c[3]

    v, raw, sym, _, row = max(cands, key=strength)
    others = {c[0] for c in cands if c[0] != v}
    if sym is None and raw.startswith("2") and counts[v] == 1 and _to_decimal(raw[1:]) in others:
        return Hit(_to_decimal(raw[1:]), row, "format", note="OCR read the ₹ sign as 2; another line confirms the value")
    if sym in ("%", "?"):
        return Hit(v, row, "format", note=f"OCR read the ₹ sign as {sym}")
    if sym is None and counts[v] == 1:
        note = "No ₹ sign found next to this amount"
        if raw.startswith("2"):
            note += "; if OCR misread ₹ as 2, the real amount is " + raw[1:]
        return Hit(v, row, "format", failed=1, note=note)
    return Hit(v, row, "format")


def date_time(rows: list[Row]) -> Optional[Hit]:
    for i, r in enumerate(rows):
        for rx in DATE_RES:
            m = rx.search(r.text)
            if not m:
                continue
            date_s = m.group(0)
            t = TIME_RE.search(r.text)
            for j in (i - 1, i + 1):
                if t is None and 0 <= j < len(rows):
                    t = TIME_RE.search(rows[j].text)
            time_s = t.group(0) if t else ""
            try:
                dt = dateparser.parse(f"{date_s} {time_s}".replace(",", " "), dayfirst=True)
            except (ValueError, OverflowError):
                continue
            note = None
            nums = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-]\d{2,4}", date_s)
            if nums and int(nums.group(1)) <= 12 and int(nums.group(2)) <= 12 and nums.group(1) != nums.group(2):
                note = "Read as day/month (Indian format)"
            if not time_s:
                note = (note + "; " if note else "") + "No time found"
            return Hit(dt.replace(tzinfo=IST), i, "format", note=note)
    return None


def status(rows: list[Row]) -> Optional[Hit]:
    for i, r in enumerate(rows):
        for label, rx in STATUS:
            if rx.search(r.text):
                return Hit(label, i, "format")
    return None


def bank(rows: list[Row], prefer: list[int]) -> tuple[Optional[Hit], Optional[Hit]]:
    names = load_list("banks.txt")
    order = [i for i in prefer if 0 <= i < len(rows)] + list(range(len(rows)))
    bank_hit = last4 = None
    for i in order:
        text = VPA_RE.sub(" ", rows[i].text)
        if bank_hit is None and (m := BANK_RE.search(text)):
            squashed = re.sub(r"\s+", "", m.group(1)).lower()
            canonical = next(n for n in names if n.replace(" ", "").lower() == squashed)
            bank_hit = Hit(canonical, i, "format")
        if last4 is None and ((m := MASK_RE.search(text)) or (m := BANK_DASH_RE.search(text))):
            last4 = Hit(m.group(1), i, "format")
        if bank_hit and last4:
            break
    return bank_hit, last4


def generic_vpas(rows: list[Row]) -> list[Hit]:
    return [Hit(m.group(0), i, "generic") for i, r in enumerate(rows) for m in VPA_RE.finditer(r.text)]


def app_id(rows: list[Row], spec: dict, how: str) -> Optional[Hit]:
    pattern = re.compile(spec.get("pattern", r"\b[A-Za-z0-9]{8,}\b"))
    for i, after in find_labels(rows, spec.get("labels", [])):
        for j, seg in [(i, after)] + [(j, rows[j].text) for j in (i + 1,) if j < len(rows)]:
            for m in pattern.finditer(seg):
                v = m.group(0)
                if re.search(r"\d", v) and not UTR_RE.fullmatch(v):
                    return Hit(v, j, how)
    return None


def note(rows: list[Row], labels: list[str], how: str) -> Optional[Hit]:
    for i, after in find_labels(rows, labels):
        text = after.strip() or (rows[i + 1].text.strip() if i + 1 < len(rows) else "")
        if text:
            return Hit(text, i, how)
    return None


def as_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")
