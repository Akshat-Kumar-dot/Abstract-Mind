"""The LLM step: grounding drops anything not in the paper, and nothing is sent
to a provider unless the person allowed it for that upload."""
from app.extraction.core.text import normalize
from app.extraction.core.verify import grounded, orcid_ok
from app.extraction.ingest import layout
from app.extraction.llm import client as llm_client
from app.extraction.paper import header, llm_fill, zones
from app.extraction.service import load, run


def test_orcid_checksum():
    assert orcid_ok("0000-0002-1825-0097")
    assert not orcid_ok("0000-0002-1825-0098")


def test_grounding():
    hay = normalize("Alice Kumar¹, Department of Physics, IIT Delhi")
    assert grounded("Alice Kumar", hay)
    assert not grounded("Bob Mehta", hay)


def _header_with_no_authors(fixtures):
    doc = load((fixtures / "lncs.pdf").read_bytes(), "lncs.pdf")
    layout.clean(doc)
    z = zones.split(doc)
    h = header.parse(z)
    h.authors = []                        # pretend the rules found nobody
    return h, z


def test_llm_values_not_in_the_paper_are_dropped(fixtures, monkeypatch):
    h, z = _header_with_no_authors(fixtures)
    monkeypatch.setattr(llm_client, "provider", lambda: "gemini")
    monkeypatch.setattr(llm_client, "extract_json", lambda *a, **k: {
        "title": "A Zone-Based Method for Author Extraction",
        "authors": [
            {"name": "Bob Mehta", "email": "bob.mehta@ox.ac.uk", "affiliations": ["University of Oxford, Oxford OX1 3QD, UK"], "corresponding": True},
            {"name": "Invented Person", "email": "ghost@nowhere.org", "affiliations": ["Imaginary University"]},
        ],
        "keywords": [],
    })
    info, _ = llm_fill.fill(h, z, ["x"], allow_ai=True)
    assert info["used"] is True
    assert [a.name for a in h.authors] == ["Bob Mehta"]
    assert h.authors[0].email == "bob.mehta@ox.ac.uk"
    assert "dropped" in info["reason"]


def test_nothing_is_sent_without_permission(fixtures, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("text was sent to an LLM without permission")

    h, z = _header_with_no_authors(fixtures)
    monkeypatch.setattr(llm_client, "provider", lambda: "gemini")
    monkeypatch.setattr(llm_client, "extract_json", refuse)
    info, _ = llm_fill.fill(h, z, [], allow_ai=False)
    assert info["used"] is False
    result = run((fixtures / "lncs.pdf").read_bytes(), "lncs.pdf")      # allow_ai defaults to False
    assert result["llm"]["used"] is False
