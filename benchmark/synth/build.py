"""Compile journal templates filled with made-up authors into test papers.

    python benchmark/synth/build.py              every style, PER_STYLE papers each
    python benchmark/synth/build.py ieee-journal only that style (handy while fixing one)

Writes benchmark/data/t-<style>/<id>.pdf and <id>.truth.json, which score.py
grades like the real papers. Needs Tectonic (a LaTeX engine):
    conda create -n am-latex -c conda-forge tectonic
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from people import make_paper
from templates import SHORT_AFFILIATIONS, STYLES

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
PER_STYLE = 6
TECTONIC = os.getenv("TECTONIC") or shutil.which("tectonic") or str(
    Path.home() / "anaconda3" / "envs" / "am-latex" / "Library" / "bin" / "tectonic.exe")


def truth_for(paper, style: str, shows: dict) -> dict:
    t = paper.truth(f"t-{style}")
    for a, src in zip(t["authors"], paper.authors):
        if not shows["corresponding"]:
            a["corresponding"] = False
        if shows["emails"] == "corresponding" and not src.corresponding:
            a["emails"] = []
        if shows["emails"] == "none":
            a["emails"] = []
        if style in SHORT_AFFILIATIONS:
            a["affiliations"] = [f"{f.institution}, {f.country}" for f in src.affiliations]
    return t


def build(style: str) -> int:
    render, shows = STYLES[style]
    out = DATA / f"t-{style}"
    out.mkdir(parents=True, exist_ok=True)
    made = 0
    for i in range(PER_STYLE):
        paper = make_paper(1000 * (list(STYLES).index(style) + 1) + i)
        pdf = out / f"{paper.id}.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "paper.tex"
            src.write_text(render(paper), encoding="utf-8")
            r = subprocess.run([TECTONIC, "--keep-logs", "--chatter", "minimal", str(src)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                print(f"  {style} {paper.id}: LaTeX failed\n" + (r.stderr or r.stdout)[-1500:], file=sys.stderr)
                continue
            shutil.copyfile(Path(tmp) / "paper.pdf", pdf)
        (out / f"{paper.id}.truth.json").write_text(
            json.dumps(truth_for(paper, style, shows), indent=1, ensure_ascii=False), encoding="utf-8")
        made += 1
    print(f"{style:20} {made}/{PER_STYLE} papers")
    return made


if __name__ == "__main__":
    for s in (sys.argv[1:] or STYLES):
        build(s)
