"""Build the test set of real papers.

    python benchmark/fetch.py --pick       choose papers for every style -> benchmark/corpus.json
    python benchmark/fetch.py              download the chosen papers -> benchmark/data/ (git-ignored)

Each paper comes from PubMed Central's open-access bucket as a PDF plus the
publisher's JATS XML; jats.py turns the XML into the true answers. Only the
list of paper ids (corpus.json) is kept in git: the PDFs are copyrighted and
the answers contain researchers' emails, so both stay on this machine.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

import jats

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus.json"
DATA = HERE / "data"
BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PER_STYLE = 5

# One entry per typesetting style: publishers lay out the first page differently.
STYLES = {
    "plos": "PLoS One", "plos-compbio": "PLoS Comput Biol", "nature-scirep": "Sci Rep",
    "nature-commun": "Nat Commun", "bmc": "BMC Bioinformatics", "frontiers": "Front Psychol",
    "mdpi-sensors": "Sensors (Basel)", "mdpi-ijerph": "Int J Environ Res Public Health", "elife": "Elife",
    "peerj": "PeerJ", "elsevier-heliyon": "Heliyon", "cell-reports": "Cell Rep", "oxford-nar": "Nucleic Acids Res",
    "oxford-bioinformatics": "Bioinformatics", "wiley-ecolevol": "Ecol Evol", "wiley-advsci": "Adv Sci (Weinh)",
    "springer-scidata": "Sci Data", "jmir": "J Med Internet Res", "royalsociety": "R Soc Open Sci",
    "acs-omega": "ACS Omega", "bmj-open": "BMJ Open", "wolters-medicine": "Medicine (Baltimore)",
    "pnas": "Proc Natl Acad Sci U S A", "science-advances": "Sci Adv", "cureus": "Cureus",
    "india-ophthalmology": "Indian J Ophthalmol", "india-familymed": "J Family Med Prim Care",
    "ieee-jtehm": "IEEE J Transl Eng Health Med",
}

client = httpx.Client(timeout=60, follow_redirects=True,
                      headers={"User-Agent": "AbstractMind-benchmark/0.1 (building a small research test set)"})


def candidates(journal: str) -> list[dict]:
    q = f'JOURNAL:"{journal}" AND OPEN_ACCESS:y AND IN_PMC:y AND PUB_YEAR:[2019 TO 2025] AND PUB_TYPE:"research-article"'
    r = client.get(SEARCH, params={"query": q, "format": "json", "resultType": "lite", "pageSize": 40})
    r.raise_for_status()
    return [x for x in r.json()["resultList"]["result"] if x.get("pmcid")]


def has_pdf(pmcid: str) -> bool:
    return client.head(f"{BUCKET}/{pmcid}.1/{pmcid}.1.pdf").status_code == 200


def pick() -> None:
    corpus = []
    for style, journal in STYLES.items():
        chosen = []
        for x in candidates(journal):
            if len(chosen) == PER_STYLE:
                break
            if has_pdf(x["pmcid"]):
                chosen.append({"style": style, "id": x["pmcid"], "title": x.get("title", "")[:120]})
        print(f"{style:24} {len(chosen)} papers")
        corpus += chosen
    CORPUS.write_text(json.dumps(corpus, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(corpus)} papers listed in {CORPUS.name}")


def download() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    for i, p in enumerate(corpus, 1):
        folder = DATA / p["style"]
        folder.mkdir(parents=True, exist_ok=True)
        pdf, xml, truth = (folder / f"{p['id']}{ext}" for ext in (".pdf", ".xml", ".truth.json"))
        base = f"{BUCKET}/{p['id']}.1/{p['id']}.1"
        try:
            if not pdf.exists():
                pdf.write_bytes(client.get(base + ".pdf").raise_for_status().content)
            if not xml.exists():
                xml.write_bytes(client.get(base + ".xml").raise_for_status().content)
        except Exception as e:                              # one bad paper shouldn't stop the rest
            print(f"  skip {p['id']}: {e}", file=sys.stderr)
            continue
        # The answers are always rebuilt from the saved XML, so fixes to jats.py apply everywhere.
        truth.write_text(json.dumps({**p, **jats.parse(xml.read_bytes())}, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"[{i}/{len(corpus)}] {p['style']} {p['id']}")
        time.sleep(0.3)                                     # be gentle with the servers


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick", action="store_true", help="choose a fresh set of papers")
    args = ap.parse_args()
    pick() if args.pick or not CORPUS.exists() else None
    download()
