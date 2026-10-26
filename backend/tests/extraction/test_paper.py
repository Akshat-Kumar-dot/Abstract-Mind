import pytest

from app.extraction.service import run
from app.extraction.paper.affiliations import parse as parse_affiliation
from app.extraction.paper.header import split_names
from app.extraction.paper.names import split_name

CITED = {"Smith", "Lee", "Wong", "Patel", "Garcia", "Chen", "Raman"}


def extract(fixtures, name):
    return run((fixtures / name).read_bytes(), name)


def field(fields, key):
    return next(f for f in fields if f["key"] == key)


def paper_field(result, key):
    for g in result["groups"]:
        for f in g["fields"]:
            if f["key"] == key:
                return f
    raise KeyError(key)


def authors(result):
    return [{f["key"]: f["value"] for f in a["fields"]} for a in result["authors"]]


EXPECTED = {
    "ieee.pdf": {
        "title": "Reading Submission Metadata from Unpublished Manuscripts with Layout Rules",
        "names": ["Aarav Sharma", "Meera Iyer", "Daniel Okafor"],
        "emails": ["aarav.sharma@cse.iitd.ac.in", "m.iyer@ed.ac.uk", "dokafor@microsoft.com"],
        "countries": ["India", "UK", "USA"],
        "corresponding": [False, False, False],
        "keywords": ["metadata extraction", "document layout", "research papers"],
        "references": 12,
    },
    "lncs.pdf": {
        "title": "A Zone-Based Method for Author Extraction",
        "names": ["Alice Kumar", "Bob Mehta", "Carol Smith"],
        "emails": ["alice@iisc.ac.in", "bob.mehta@ox.ac.uk", "carol@iisc.ac.in"],
        "countries": ["India", "UK", "India"],
        "corresponding": [False, True, False],
        "keywords": ["metadata", "zone segmentation", "author linking"],
        "references": 8,
    },
    "nature.pdf": {
        "title": "Mapping glacier retreat with satellite radar and machine learning",
        "names": ["Asha Raman", "Lukas Brandt", "Wei Zhang", "Fatima Okoye"],
        "emails": ["a.raman@geo.uzh.ch", None, None, None],
        "countries": ["Switzerland", "Switzerland", "China", "Switzerland"],
        "corresponding": [True, False, False, False],
        "keywords": [],
        "references": 20,
    },
    "manuscript.docx": {
        "title": "Soil Moisture Estimation from Sentinel-1 Data over Indian Farmland",
        "names": ["Ravi Sharma", "Priya Nair"],
        "emails": ["ravi.sharma@du.ac.in", "priya.nair@ed.ac.uk"],
        "countries": ["India", "United Kingdom"],
        "corresponding": [False, True],
        "keywords": ["soil moisture", "Sentinel-1", "radar", "agriculture"],
        "references": 5,
    },
    "acm.tex": {
        "title": "Paper Mind: Reading Manuscripts So Authors Don't Have To",
        "names": ["Ishaan Verma", "Sara Lindqvist"],
        "emails": ["ishaan.verma@iiitd.ac.in", "sara.lindqvist@kth.se"],
        "countries": ["India", "Sweden"],
        "corresponding": [False, True],
        "keywords": ["metadata", "LaTeX", "submission forms"],
        "references": 2,
    },
    "ieee.tex": {
        "title": "Fast Header Parsing for Conference Submissions",
        "names": ["Kavya Rao", "Tom Becker"],
        "emails": ["kavya.rao@nitt.edu", "becker@in.tum.de"],
        "countries": ["India", "Germany"],
        "corresponding": [False, False],
        "keywords": ["parsing", "headers"],
        "references": 3,
    },
    "elsarticle.tex": {
        "title": "Groundwater Recharge in the Deccan Traps",
        "names": ["Neha Kulkarni", "Rahul Deshmukh"],
        "emails": ["neha.k@iitb.ac.in", None],
        "countries": ["India", "India"],
        "corresponding": [True, False],
        "keywords": ["groundwater", "basalt", "recharge"],
        "references": None,
    },
}


@pytest.mark.parametrize("name", list(EXPECTED))
def test_manuscript(fixtures, name):
    r = extract(fixtures, name)
    exp = EXPECTED[name]
    assert r["kind"] == "paper"
    assert paper_field(r, "title")["value"] == exp["title"]
    got = authors(r)
    assert [a["name"] for a in got] == exp["names"]
    assert [a["email"] for a in got] == exp["emails"]
    assert [a["country"] for a in got] == exp["countries"]
    assert [a["corresponding"] for a in got] == exp["corresponding"]
    assert paper_field(r, "keywords")["value"] == exp["keywords"]
    assert paper_field(r, "references")["value"] == exp["references"]
    assert paper_field(r, "abstract")["value"]


@pytest.mark.parametrize("name", list(EXPECTED))
def test_no_cited_author_leaks(fixtures, name):
    """Names cited in the body or listed in the references never become authors."""
    got = {n.split()[-1] for n in (a["name"] for a in authors(extract(fixtures, name)))}
    real = {n.split()[-1] for n in EXPECTED[name]["names"]}   # e.g. Carol Smith really wrote lncs.pdf
    assert not (got & CITED) - real
    assert got == real


def test_ieee_layout_links_each_author_to_their_own_column(fixtures):
    got = authors(extract(fixtures, "ieee.pdf"))
    assert got[0]["institution"] == "IIT Delhi"
    assert got[1]["institution"] == "University of Edinburgh"
    assert got[2]["city"] == "Redmond"


def test_declarations_and_counts(fixtures):
    r = extract(fixtures, "manuscript.docx")
    assert paper_field(r, "grant_ids")["value"] == ["ISRO/RES/3/812/2022"]
    assert paper_field(r, "data_urls")["value"] == ["https://zenodo.org/records/1234567"]
    assert "Supervision" in paper_field(r, "credit_roles")["value"]
    assert paper_field(r, "figures")["value"] == 2
    assert paper_field(r, "tables")["value"] == 1
    ieee = extract(fixtures, "ieee.pdf")
    assert paper_field(ieee, "grant_ids")["value"] == ["CRG/2021/004567"]


def test_acm_orcid(fixtures):
    got = authors(extract(fixtures, "acm.tex"))
    assert got[0]["orcid"] == "0000-0002-1825-0097"


@pytest.mark.parametrize("raw,expected", [
    ("Alice Kumar^{1}, Bob Mehta^{2,*}, and Carol Smith^{1}", [("Alice Kumar", ["1"]), ("Bob Mehta", ["2", "*"]), ("Carol Smith", ["1"])]),
    ("John Smith1,2, Jane Doe2", [("John Smith", ["1", "2"]), ("Jane Doe", ["2"])]),
    ("1st Kavya Rao", [("Kavya Rao", [])]),
    ("A. Kumar, Member, IEEE, and R. Mehta, Fellow, IEEE", [("A. Kumar", []), ("R. Mehta", [])]),
])
def test_split_names(raw, expected):
    assert [(n, m) for n, m, _ in split_names(raw)] == expected


@pytest.mark.parametrize("name,first,last", [
    ("Ludwig van Beethoven", "Ludwig", "van Beethoven"),
    ("A. K. Singh", "A. K.", "Singh"),
    ("John SMITH", "John", "SMITH"),
    ("Smith, John", "John", "Smith"),
])
def test_split_name(name, first, last):
    assert split_name(name) == (first, last)


def test_parse_affiliation_indian_address():
    p = parse_affiliation("Department of CSE, Indian Institute of Science, Bengaluru, Karnataka 560012, India")
    assert p == {"department": "Department of CSE", "institution": "Indian Institute of Science", "city": "Bengaluru", "country": "India"}


def test_nature_layout_without_headings(fixtures):
    """No Abstract/Introduction/References headings, notes run together in one
    footnote, a marker that means equal contribution, bold run-in headings."""
    r = extract(fixtures, "nature.pdf")
    assert paper_field(r, "abstract")["value"].startswith("Glaciers are retreating")
    assert paper_field(r, "doi")["value"] == "10.1038/s41586-023-01234-5"
    assert paper_field(r, "publisher")["value"].startswith("Springer Nature")
    assert paper_field(r, "journal")["value"] == "Nature"
    assert paper_field(r, "received")["value"] == "2 January 2023"
    assert paper_field(r, "acknowledgments")["value"].startswith("We thank")
    assert paper_field(r, "grant_ids")["value"] == ["200021-182345"]
    equal = [any(f["key"] == "equal" for f in a["fields"]) for a in r["authors"]]
    assert equal == [True, True, False, False]
