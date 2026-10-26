"""header_reader: linked records, checks, and the name forms seen across journals."""
from pathlib import Path

import pytest

from app.extraction import service
from app.extraction.header_reader import read_pdf
from app.extraction.header_reader.emails import name_score
from app.extraction.header_reader.names import split_people

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.mark.parametrize("line, expected", [
    ("Junrong Song^{1*}, Yuanli Gong^{1} and Kun Qian^{1,2}",
     [("Junrong Song", ["1", "*"]), ("Yuanli Gong", ["1"]), ("Kun Qian", ["1", "2"])]),
    # degrees after a name are not people (JMIR, Wolters Kluwer)
    ("Megan Threats, MSLS, PhD; Morgan Gray, MSLS", [("Megan Threats", []), ("Morgan Gray", [])]),
    ("Hao Yang, RN, MBA, BSN^{a,b}, Xihong Wang, RN^{c}", [("Hao Yang", ["a", "b"]), ("Xihong Wang", ["c"])]),
    # "A | B" (Wiley)
    ("Takuya Okabe^{1} | Jin Yoshimura^{1,2}", [("Takuya Okabe", ["1"]), ("Jin Yoshimura", ["1", "2"])]),
    # markers printed after the comma (ACS)
    ("Arjun Singh,^{†} Xiaoming Liu,^{‡} and Omar El-Sayed^{‡}",
     [("Arjun Singh", ["†"]), ("Xiaoming Liu", ["‡"]), ("Omar El-Sayed", ["‡"])]),
])
def test_split_people(line, expected):
    assert split_people(line) == expected


def test_name_score_prefers_the_right_person():
    assert name_score("bob.mehta@ox.ac.uk", "Bob Mehta") >= 80
    assert name_score("bob.mehta@ox.ac.uk", "Alice Kumar") < 50


def test_records_are_linked_by_id():
    paper = read_pdf((FIXTURES / "lncs.pdf").read_bytes())
    names = [a.name for a in paper.authors]
    assert names == ["Alice Kumar", "Bob Mehta", "Carol Smith"]
    assert [a.id for a in paper.authors] == ["A1", "A2", "A3"]
    # every email points back at the author that points at it
    for e in paper.emails:
        owner = next(a for a in paper.authors if a.id == e.author_id)
        assert owner.email_id == e.id
    assert {paper.email_of(a) for a in paper.authors} == {"alice@iisc.ac.in", "bob.mehta@ox.ac.uk", "carol@iisc.ac.in"}
    # authors sharing marker 1 share one affiliation record
    assert paper.authors[0].affiliation_ids == paper.authors[2].affiliation_ids == ["F1"]
    assert all(c.ok for c in paper.checks), [c.detail for c in paper.checks if not c.ok]
    assert paper.trace and paper.trace[0].startswith("layout:")


def test_doubtful_values_are_flagged_not_hidden():
    paper = read_pdf((FIXTURES / "nature.pdf").read_bytes())
    linked = [a for a in paper.authors if paper.email_of(a)]
    assert [a.name for a in linked] == ["Asha Raman"]          # one printed email, one owner
    assert paper.authors[0].corresponding
    by_name = {c.name: c for c in paper.checks}
    assert by_name["everything read is in the paper"].ok


def test_app_result_carries_the_links():
    out = service.run((FIXTURES / "lncs.pdf").read_bytes(), "lncs.pdf", kind="paper")
    links = out["links"]
    assert [a["id"] for a in links["authors"]] == ["A1", "A2", "A3"]
    assert {f["id"] for f in links["affiliations"]} == {"F1", "F2"}
    assert any(c["name"] == "every email belongs to one author" for c in links["checks"])
