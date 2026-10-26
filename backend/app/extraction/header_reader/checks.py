"""Checks on a read paper. Each one says plainly what is missing or doubtful,
so nothing doubtful is passed off as certain."""
from __future__ import annotations

import re
import unicodedata

from .model import Check, Paper


def _words(text: str) -> set[str]:
    """Words, split on hyphens too: a title hyphenated across lines is still found."""
    text = unicodedata.normalize("NFKC", text).lower()
    return {w.strip(".") for w in re.findall(r"[\w.]{2,}", text) if len(w.strip(".")) >= 2}


def run(paper: Paper, paper_text: str) -> list[Check]:
    checks = [Check("title found", bool(paper.title), "" if paper.title else "No title could be read."),
              Check("authors found", bool(paper.authors), "" if paper.authors else "No author names under the title.")]
    if not paper.authors:
        return checks

    without = [a.name for a in paper.authors if not a.affiliation_ids]
    checks.append(Check("every author has an affiliation", not without,
                        f"No affiliation for: {', '.join(without)}." if without else ""))

    used = {f for a in paper.authors for f in a.affiliation_ids}
    unused = [f.text for f in paper.affiliations if f.id not in used]
    checks.append(Check("every affiliation belongs to an author", not unused,
                        f"Not linked to anyone: {'; '.join(unused)}." if unused else ""))

    loose = [e.address for e in paper.emails if not e.author_id]
    checks.append(Check("every email belongs to one author", not loose,
                        f"Couldn't tell whose: {', '.join(loose)}." if loose else ""))

    have = {f.marker for f in paper.affiliations if f.marker} | set(paper.footnotes)
    missing = sorted({m for a in paper.authors for m in a.markers if m.isalnum() and m not in have})
    checks.append(Check("every author marker has an affiliation", not missing,
                        f"No affiliation found for marker(s) {', '.join(missing)}." if missing else ""))

    words = _words(paper_text)
    compact = re.sub(r"\s+", "", paper_text.lower())          # an email can be broken over a line
    values = [paper.title] + [a.name for a in paper.authors] + [f.text for f in paper.affiliations]
    not_in = [v for v in values if v and not _words(v) <= words]
    not_in += [e.address for e in paper.emails if e.address not in compact
               and not all(part in compact for part in e.address.split("@"))]      # "{alice,carol}@x" form
    checks.append(Check("everything read is in the paper", not not_in,
                        f"Not found word for word: {'; '.join(not_in)}." if not_in else ""))
    return checks
