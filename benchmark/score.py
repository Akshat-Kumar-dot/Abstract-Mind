"""Grade a paper reader against the true answers in benchmark/data/.

    python benchmark/score.py                      score the old header parser (the baseline)
    python benchmark/score.py --engine new         score header_reader, the one the app uses
    python benchmark/score.py --compare            both, side by side; exits 1 if new is worse anywhere
    python benchmark/score.py --show emails        list every paper where emails went wrong or missing

"Wrong" (a value given to the wrong author, or one that isn't in the paper) is
counted apart from "missed" (left empty): wrong is worse, because nobody checks
a value that looks filled in.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
DATA = HERE / "data"


# ------------------------------------------------------------ the readers, in one shape
def read_current(pdf: Path) -> dict:
    """The old header parser, kept as the baseline. Its answers never change, so
    they're cached next to the paper (delete *.current.json to recompute)."""
    cache = pdf.with_name(pdf.stem + ".current.json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    out = _run_current(pdf)
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def _run_current(pdf: Path) -> dict:
    from app.extraction.header_reader.model import Paper
    from app.extraction.paper import pipeline
    from app.extraction.service import run
    reader, pipeline.read_header = pipeline.read_header, lambda doc: Paper()    # finds nothing: the old parser is used
    try:
        r = run(pdf.read_bytes(), pdf.name, "paper")
    finally:
        pipeline.read_header = reader
    fields = {f["key"]: f["value"] for g in r["groups"] for f in g["fields"]}
    authors = []
    for a in r["authors"]:
        f = {x["key"]: x["value"] for x in a["fields"]}
        authors.append({"name": f.get("name") or a.get("name") or "",
                        "emails": [f["email"]] if f.get("email") else [],
                        "affiliations": list(f.get("affiliations") or []),
                        "corresponding": bool(f.get("corresponding"))})
    return {"title": fields.get("title") or "", "authors": authors}


def read_new(pdf: Path) -> dict:
    from app.extraction.header_reader import read_pdf          # the rebuilt reader
    return read_pdf(pdf.read_bytes()).as_benchmark()


ENGINES = {"old": read_current, "new": read_new}


# ------------------------------------------------------------ comparing
def plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9@. ]+", " ", s).strip()


def same_name(a: str, b: str) -> bool:
    return fuzz.token_sort_ratio(plain(a), plain(b)) >= 85


def same_affiliation(a: str, b: str) -> bool:
    return fuzz.token_set_ratio(plain(a), plain(b)) >= 80


def grade(truth: dict, got: dict) -> dict:
    """Counts for one paper. Each metric is (right, wrong, total)."""
    c = defaultdict(int)
    c["title_total"] = 1
    c["title_right"] = int(fuzz.ratio(plain(truth["title"]), plain(got["title"])) >= 95)

    # pair every true author with the predicted author of the same name
    pairs, used = [], set()
    for t in truth["authors"]:
        match = next((i for i, g in enumerate(got["authors"]) if i not in used and same_name(t["name"], g["name"])), None)
        if match is not None:
            used.add(match)
        pairs.append((t, None if match is None else got["authors"][match], match))
    c["authors_total"] = len(truth["authors"])
    c["authors_right"] = sum(1 for _, g, _ in pairs if g is not None)
    c["authors_wrong"] = len(got["authors"]) - len(used)                 # people who aren't authors
    order = [m for _, _, m in pairs if m is not None]
    c["order_total"], c["order_right"] = 1, int(order == sorted(order) and c["authors_right"] == c["authors_total"])

    for t, g, _ in pairs:
        if t["emails"]:                                                    # the answer key knows this email
            c["emails_total"] += 1
            given = [e.lower() for e in (g["emails"] if g else [])]
            if any(e in t["emails"] for e in given):
                c["emails_right"] += 1
            elif given:
                c["emails_wrong"] += 1
        for aff in t["affiliations"]:
            c["affils_total"] += 1
            if g and any(same_affiliation(aff, x) for x in g["affiliations"]):
                c["affils_right"] += 1
        if g and t["affiliations"]:
            c["affils_wrong"] += sum(1 for x in g["affiliations"] if not any(same_affiliation(x, a) for a in t["affiliations"]))
        if t["corresponding"]:
            c["corr_total"] += 1
            c["corr_right"] += int(bool(g and g["corresponding"]))
        elif g and g["corresponding"]:
            c["corr_wrong"] += 1
    return dict(c)


METRICS = ["title", "authors", "order", "emails", "affils", "corr"]


def summary(counts: list[dict]) -> dict:
    out = {}
    for m in METRICS:
        total = sum(x.get(f"{m}_total", 0) for x in counts)
        out[m] = {"right": sum(x.get(f"{m}_right", 0) for x in counts),
                  "wrong": sum(x.get(f"{m}_wrong", 0) for x in counts), "total": total}
    return out


def pct(s: dict) -> str:
    if not s["total"]:
        return "    -   "
    right = 100 * s["right"] / s["total"]
    return f"{right:5.1f}%" + (f" w{s['wrong']}" if s["wrong"] else "   ").ljust(5)


# ------------------------------------------------------------ running
def papers():
    for truth_file in sorted(DATA.glob("*/*.truth.json")):
        truth = json.loads(truth_file.read_text(encoding="utf-8"))
        if truth["authors"]:
            yield truth, truth_file.with_name(truth_file.name.replace(".truth.json", ".pdf"))


def run(engine: str, show: str | None = None) -> dict:
    by_style, details = defaultdict(list), []
    for truth, pdf in papers():
        try:
            got = ENGINES[engine](pdf)
        except Exception as e:                     # a crash counts as getting everything wrong
            print(f"  {engine} crashed on {pdf.name}: {type(e).__name__}: {e}", file=sys.stderr)
            got = {"title": "", "authors": []}
        g = grade(truth, got)
        by_style[truth["style"]].append(g)
        details.append((truth, got, g))
        if show and (g.get(f"{show}_wrong") or g.get(f"{show}_right", 0) < g.get(f"{show}_total", 0)):
            print(f"\n--- {truth['style']} {truth['id']}  ({show}: {g.get(show + '_right', 0)}/{g.get(show + '_total', 0)}, wrong {g.get(show + '_wrong', 0)})")
            for t in truth["authors"]:
                p = next((a for a in got["authors"] if same_name(t["name"], a["name"])), None)
                print(f"  {t['name']:28} true: {t['emails'] or t['affiliations'][:1] if show in ('emails', 'affils') else t['corresponding']}")
                print(f"  {'':28}  got: {(p['emails'] if show == 'emails' else p['affiliations'][:1] if show == 'affils' else p['corresponding']) if p else 'author not found'}")
    return {"styles": {s: summary(c) for s, c in sorted(by_style.items())},
            "all": summary([g for c in by_style.values() for g in c]), "papers": len(details)}


def table(result: dict, title: str) -> None:
    print(f"\n{title}  ({result['papers']} papers; w = wrong, not just missing)")
    print(f"{'style':24}" + "".join(f"{m:>13}" for m in METRICS))
    for style, s in result["styles"].items():
        print(f"{style:24}" + "".join(f"{pct(s[m]):>13}" for m in METRICS))
    print(f"{'ALL':24}" + "".join(f"{pct(result['all'][m]):>13}" for m in METRICS))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=ENGINES, default="old")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--show", choices=METRICS)
    args = ap.parse_args()
    if not args.compare:
        table(run(args.engine, args.show), f"reader: {args.engine}")
        return 0
    old, new = run("old"), run("new")
    table(old, "reader: old")
    table(new, "reader: new")
    worse = []
    for m in METRICS:
        o, n = old["all"][m], new["all"][m]
        if n["right"] < o["right"] or n["wrong"] > o["wrong"]:
            worse.append(f"{m}: right {o['right']}->{n['right']}, wrong {o['wrong']}->{n['wrong']}")
    print("\nnew reader is worse on: " + "; ".join(worse) if worse else "\nnew reader is at least as good on every field")
    return 1 if worse else 0


if __name__ == "__main__":
    sys.exit(main())
