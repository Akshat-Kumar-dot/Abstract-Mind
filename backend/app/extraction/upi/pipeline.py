"""UPI receipt pipeline: rows -> app template -> generic rules -> checks."""
from __future__ import annotations

from typing import Optional

from ..core.confidence import make
from ..core.models import Document, Evidence, Field, Result, group
from . import apps, matcher
from .matcher import Hit
from .rows import Row, build_rows
from .validators import amount_ok, date_ok, utr_ok

NOT_PROOF = ("Extracted, not verified: a receipt or screenshot can be edited. Match the UTR and amount "
             "against your bank statement or payment gateway before treating this as proof of payment.")


def run(doc: Document) -> Result:
    res = Result(kind="upi", file_type=doc.source, pages=doc.pages, warnings=list(doc.warnings))
    rows = build_rows(doc.blocks)
    text = "\n".join(r.text for r in rows)
    key, tpl = apps.detect(text)
    generic = apps.templates()["generic"]
    tf, gf = tpl.get("fields", {}), generic.get("fields", {})

    def both(fn, name: str, whole_spec: bool = False):
        """The app template first, then the generic rules for whatever it missed."""
        def spec(fields: dict):
            s = fields.get(name, {})
            return s if whole_spec else s.get("labels", [])
        hit = fn(rows, spec(tf), "template") if key != "generic" and name in tf else None
        if hit is None or (isinstance(hit, tuple) and not any(hit)):
            hit = fn(rows, spec(gf), "generic")
        return hit

    utr = both(matcher.utr, "utr")
    app_txn = both(matcher.app_id, "app_txn_id", whole_spec=True)
    if app_txn is not None and utr is not None and app_txn.value == utr.value:
        app_txn = None
    recv_name, recv_vpa = both(matcher.party, "receiver")
    send_name, send_vpa = both(matcher.party, "sender")
    if recv_vpa is None and send_vpa is None:
        vpas = matcher.generic_vpas(rows)
        if vpas:
            recv_vpa = Hit(vpas[0].value, vpas[0].row, "generic", note="No To/From label; first UPI ID on the receipt", failed=1)
            if len(vpas) > 1:
                send_vpa = Hit(vpas[1].value, vpas[1].row, "generic", note="No To/From label; second UPI ID on the receipt", failed=1)
    amt = matcher.amount(rows)
    when = matcher.date_time(rows)
    st = matcher.status(rows)
    prefer = [x.row for x in (send_name, send_vpa) if x is not None and x.row is not None]
    prefer += [p + d for p in prefer for d in (1, 2)]
    bank, last4 = matcher.bank(rows, prefer)
    memo = both(matcher.note, "note")

    app_name = tpl.get("app") if key != "generic" else None
    res.groups = [
        group("transaction", "Transaction", [
            _field("amount", "Amount (₹)", amt, rows, fmt=lambda v: f"{v:.2f}", failed=amount_ok(amt.value) if amt else 0),
            _field("status", "Status", st, rows),
            _field("datetime", "Date and time (IST)", when, rows, fmt=matcher.as_iso, failed=date_ok(when.value) if when else 0),
            _field("utr", "UTR / UPI reference", utr, rows, failed=utr_ok(utr.value if utr else None, text)),
            _field("app_txn_id", "App transaction ID", app_txn, rows),
            make("app", "Payment app", app_name, "template" if app_name else "generic", base=0.9,
                 note=None if app_name else "App not recognised; generic rules were used"),
        ]),
        group("parties", "Parties", [
            _field("receiver_name", "Paid to", recv_name, rows),
            _field("receiver_upi", "Receiver UPI ID", recv_vpa, rows),
            _field("sender_name", "Paid from", send_name, rows),
            _field("sender_upi", "Sender UPI ID", send_vpa, rows),
            _field("bank", "Bank", bank, rows, base=0.85),
            _field("account_last4", "Account (last 4 digits)", last4, rows, base=0.88),
        ]),
        group("other", "Other", [_field("note", "Note / message", memo, rows, base=0.8)]),
    ]
    res.warnings.append(NOT_PROOF)
    if not rows:
        res.warnings.append("No text was found in this file.")
    return res


def _field(key: str, label: str, hit: Optional[Hit], rows: list[Row], fmt=None, failed: int = 0, base: Optional[float] = None) -> Field:
    if hit is None or hit.value is None:
        return make(key, label, None)
    value = fmt(hit.value) if fmt else hit.value
    source = {"template": "template", "generic": "generic", "format": "rule"}[hit.how]
    ev = None
    if hit.row is not None and 0 <= hit.row < len(rows):
        r = rows[hit.row]
        ev = Evidence(page=r.blocks[0].page if r.blocks else None, text=r.text)
    return make(key, label, value, source, failed=failed + hit.failed, base=base, evidence=ev, note=hit.note)
