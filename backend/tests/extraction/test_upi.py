import pytest

from app.extraction.service import run
from app.extraction.upi import matcher
from app.extraction.upi.rows import Row
from app.extraction.core.models import Block

EXPECTED = {
    "phonepe.png": {"amount": "1250.00", "status": "Successful", "datetime": "2025-10-09T14:15:00+05:30", "utr": "528212345678",
                    "app_txn_id": "T2510091415223344556677", "app": "PhonePe", "receiver_name": "RAMESH KIRANA STORE",
                    "receiver_upi": "ramesh.store@ybl", "bank": "State Bank of India", "account_last4": "4821"},
    "gpay.png": {"amount": "500.00", "status": "Successful", "datetime": "2025-10-09T18:42:00+05:30", "utr": "412398765432",
                 "app_txn_id": "CICAgKDx8vWhNA", "app": "Google Pay", "receiver_name": "ANJALI GUPTA",
                 "receiver_upi": "anjali.g@okhdfcbank", "sender_name": "ROHIT VERMA", "sender_upi": "rohit.verma@okicici",
                 "bank": "HDFC Bank", "account_last4": "7731"},
    "paytm.pdf": {"amount": "349.00", "status": "Successful", "datetime": "2025-10-14T20:05:00+05:30", "utr": "529912340001",
                  "app": "Paytm", "receiver_name": "Swiggy", "receiver_upi": "swiggy@paytm", "sender_name": "Neel Shah",
                  "bank": "ICICI Bank", "account_last4": "9012", "note": "dinner"},
}


def values(result):
    return {f["key"]: f["value"] for g in result["groups"] for f in g["fields"]}


@pytest.mark.parametrize("name", list(EXPECTED))
def test_receipt(fixtures, name):
    r = run((fixtures / name).read_bytes(), name)
    assert r["kind"] == "upi"
    got = values(r)
    for key, want in EXPECTED[name].items():
        assert got[key] == want, key
    assert any("not verified" in w for w in r["warnings"])


def rows_of(*lines):
    out = []
    for i, (text, h) in enumerate(lines):
        b = Block(text=text, marked=text, page=1, bbox=(0, i * 40, 200, i * 40 + h))
        out.append(Row(text=text, height=h, y=i * 40, blocks=[b]))
    return out


def test_rupee_read_as_2_is_fixed_when_another_line_confirms():
    rows = rows_of(("2500", 60), ("Paid to Asha", 20), ("Debited from XX1234  500.00", 20))
    hit = matcher.amount(rows)
    assert str(hit.value) == "500.00" or hit.value == 500
    assert "2" in hit.note


def test_unconfirmed_amount_without_rupee_sign_is_flagged():
    rows = rows_of(("1,999", 60), ("Paid to Asha", 20))
    hit = matcher.amount(rows)
    assert hit.failed == 1


def test_phone_number_is_not_a_utr():
    rows = rows_of(("Call 9876543210 for help", 20), ("Paid to Asha", 20))
    assert matcher.utr(rows, [], "generic") is None
