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


# Dates as real receipts and screenshots write them, including what text
# recognition does to them (lost spaces, the O of "Oct" read as a zero).
@pytest.mark.parametrize("lines, expected", [
    (("Paid on 12-Oct-2025 08:45 PM",), "2025-10-12T20:45"),
    (("Date: 12-Oct-25", "Time: 20:45"), "2025-10-12T20:45"),
    (("12 Oct,2025 | 8:45 pm",), "2025-10-12T20:45"),
    (("12Oct2025 20:45",), "2025-10-12T20:45"),
    (("12 0ct 2025, 08:45 pm",), "2025-10-12T20:45"),
    (("Transaction date 12.10.2025 20:45",), "2025-10-12T20:45"),
    (("October 12, 2025 at 8:45 PM",), "2025-10-12T20:45"),
    (("Sunday, 12th October 2025",), "2025-10-12T00:00"),
    (("08:45 pm on 12 Oct 2025",), "2025-10-12T20:45"),
    (("12/10/2025, 20:45:10",), "2025-10-12T20:45"),
])
def test_receipt_dates(lines, expected):
    hit = matcher.date_time(rows_of(*[(t, 20) for t in lines]))
    assert hit is not None, lines
    assert hit.value.isoformat().startswith(expected), (lines, hit.value)


def test_a_date_without_a_year_gets_the_latest_matching_year_and_is_flagged():
    from datetime import datetime
    hit = matcher.date_time(rows_of(("Paid to Asha", 20), ("12 Oct, 8:45 pm", 20)))
    assert hit is not None and hit.value.month == 10 and hit.value.day == 12 and hit.value.hour == 20
    assert hit.value.date() <= datetime.now().date()            # never a date in the future
    assert hit.failed == 1 and "year" in hit.note.lower()


def test_numbers_that_are_not_dates_are_ignored():
    rows = rows_of(("UPI ref 412398765432", 20), ("Amount 1,250.00", 20), ("Version 2.10.3", 20))
    assert matcher.date_time(rows) is None


def test_time_under_its_own_label_two_rows_below_the_date():
    rows = rows_of(("Transaction Date", 20), ("12-Oct-2025", 20), ("Time", 20), ("08:45 PM", 20))
    assert matcher.date_time(rows).value.isoformat().startswith("2025-10-12T20:45")
