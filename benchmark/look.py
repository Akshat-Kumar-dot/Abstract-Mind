"""See exactly where the new reader goes wrong on one style.

    python benchmark/look.py bmc            every BMC paper
    python benchmark/look.py bmc 2          only the first two
    python benchmark/look.py --worst        the ten worst papers of all styles

For each paper: the score, the reader's trace (one line per step), and for
every author what the answer key says next to what the reader got.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from score import DATA, grade, same_name  # noqa: E402
from app.extraction.header_reader import read_pdf  # noqa: E402


def show(truth_file: Path) -> None:
    truth = json.loads(truth_file.read_text(encoding="utf-8"))
    paper = read_pdf(truth_file.with_name(truth_file.name.replace(".truth.json", ".pdf")).read_bytes())
    got = paper.as_benchmark()
    g = grade(truth, got)
    score = " | ".join(f"{m} {g.get(m + '_right', 0)}/{g.get(m + '_total', 0)}" + (f" w{g[m + '_wrong']}" if g.get(m + "_wrong") else "")
                       for m in ("authors", "emails", "affils", "corr"))
    print(f"\n=== {truth['style']} {truth['id']}  {score}")
    for t in paper.trace:
        print(f"    · {t}")
    for t in truth["authors"]:
        a = next((x for x in got["authors"] if same_name(t["name"], x["name"])), None)
        print(f"    {t['name'][:26]:26}  true {t['emails'][:1]} {'*' if t['corresponding'] else ' '} {[f[:55] for f in t['affiliations']]}")
        print(f"    {'':26}   got " + (f"{a['emails'][:1]} {'*' if a['corresponding'] else ' '} {[f[:55] for f in a['affiliations']]}" if a else "NOT FOUND"))
    extra = [x["name"] for x in got["authors"] if not any(same_name(x["name"], t["name"]) for t in truth["authors"])]
    if extra:
        print(f"    not authors but read as authors: {extra}")
    for c in paper.checks:
        if not c.ok:
            print(f"    check failed: {c.name}: {c.detail[:140]}")


def main() -> None:
    args = sys.argv[1:]
    files = sorted(DATA.glob("*/*.truth.json"))
    if args and args[0] == "--worst":
        scored = []
        for f in files:
            t = json.loads(f.read_text(encoding="utf-8"))
            g = grade(t, read_pdf(f.with_name(f.name.replace(".truth.json", ".pdf")).read_bytes()).as_benchmark())
            missed = sum(g.get(m + "_total", 0) - g.get(m + "_right", 0) + 2 * g.get(m + "_wrong", 0) for m in ("authors", "emails", "affils"))
            scored.append((missed, f))
        files = [f for _, f in sorted(scored, key=lambda x: -x[0])[:10]]
    elif args:
        files = [f for f in files if f.parent.name == args[0]][: int(args[1]) if len(args) > 1 else None]
    for f in files:
        show(f)


if __name__ == "__main__":
    main()
