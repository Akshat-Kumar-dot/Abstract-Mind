"""Repository cover pages.

University repositories and sharing sites put a sheet of their own in front of
the paper: "UvA-DARE (Digital Academic Repository) … General rights … Download
date", ResearchGate's "See discussions, stats, and author profiles", White Rose's
"This is a repository copy of …". Read as page 1, the repository's name comes
out as the title. Such a page is recognised by its stock phrases and skipped.
"""
from __future__ import annotations

import re

PHRASES = [
    r"digital academic repository", r"general rights", r"disclaimer\s*/\s*complaints", r"download date",
    r"citation for published version", r"link to publication", r"document version", r"take\s*down policy",
    r"see discussions, stats,? and author profiles", r"this is a repository copy of", r"downloaded from",
    r"copyright and moral rights", r"terms of use", r"version of record", r"published version \(apa\)",
    r"users may download and print one copy", r"you may not further distribute the material",
    r"if you believe that this document breaches copyright", r"repository", r"accepted manuscript",
    r"uploaded by", r"all content following this page was uploaded by",
]
PATTERN = re.compile("|".join(f"(?:{p})" for p in PHRASES), re.I)


def is_cover(text: str) -> bool:
    """Four or more different stock phrases on one page: a repository's sheet, not the paper."""
    found = {m.group(0).lower() for m in PATTERN.finditer(text)}
    return len(found) >= 4
