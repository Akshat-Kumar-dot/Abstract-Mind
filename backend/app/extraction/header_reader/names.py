"""Is this a person's name? And split an author line into people with markers.

    "Junrong Song^{1*}, Yuanli Gong^{1} and Kun Qian^{1,2}"
      -> [("Junrong Song", ["1", "*"]), ("Yuanli Gong", ["1"]), ("Kun Qian", ["1", "2"])]
"""
from __future__ import annotations

import re

NOT_NAME_WORDS = {
    "university", "department", "institute", "school", "college", "faculty", "laboratory", "lab", "center", "centre",
    "hospital", "research", "science", "sciences", "engineering", "technology", "abstract", "introduction", "keywords",
    "received", "accepted", "published", "correspondence", "email", "e-mail", "journal", "article", "open", "access",
    "volume", "issue", "doi", "copyright", "licence", "license", "edited", "reviewed", "citation", "original",
    "academy", "ministry", "national", "state", "key", "corporation", "inc", "ltd", "company", "group",
}
PARTICLES = {"van", "der", "den", "de", "da", "del", "della", "di", "du", "la", "le", "von", "zu", "bin", "binti",
             "al", "el", "dos", "das", "y", "ter", "ten", "st."}
SPLIT = re.compile(r"\s*(?:,|;|\band\b|&| · |\s·\s|\s\|\s)\s*", re.I)   # "AND" too (AMS capitals); "A | B" (Wiley)
MARKER_GROUP = re.compile(r"\^\{([^}]*)\}")
TRAILING_SYMBOLS = re.compile(r"[\s*†‡§¶#✉⁎∗]+$")
SYMBOL_MARKERS = "*†‡§¶#✉⁎∗"
# a degree printed after a name: "Megan Threats, MSLS, PhD; Morgan Gray, MSLS"
DEGREE = re.compile(r"^(?:Ph\.?\s?D|M\.?D|D\.?Phil|M\.?Sc|B\.?Sc|M\.?Phil|Pharm\.?D|Dr\.?PH|M\.?Ed|Jr|Sr|[A-Z]{2,6})\.?$")


def is_name(text: str) -> bool:
    """A person's name: 2–6 words, capitalised (particles aside), no digits, no institution words."""
    words = text.replace(".", ". ").split()
    if not 2 <= len(words) <= 6 or len(text) > 45 or re.search(r"\d|@|http|[:()\[\]/]", text):
        return False
    if any(w.lower().strip(".,") in NOT_NAME_WORDS for w in words):
        return False
    capitalised = [w for w in words if w[0].isupper() or w.lower() in PARTICLES]
    return len(capitalised) == len(words)


def split_people(marked: str) -> list[tuple[str, list[str]]]:
    """Author line -> (name, markers). Markers come from ^{…} groups and trailing symbols."""
    # Plain digits glued to a name are markers too: "Berg1,2" -> "Berg^{1,2}".
    marked = re.sub(r"(?<=[a-z\u00e0-\u024f])(\d+(?:,\d+)*)(?=\s*(?:,|;|\band\b|&|$))", r"^{\1}", marked)
    # ACS prints markers after the comma: "Singh,^{†} Liu,^{‡}" -> "Singh^{†}, Liu^{‡}"
    marked = re.sub(r",\s*((?:\^\{[^}]*\})+)", r"\1,", marked)
    # Keep each name's markers with it: "A^{1}, B^{2}" splits on the commas *between* people,
    # so first protect commas inside marker groups.
    protected = MARKER_GROUP.sub(lambda m: "^{" + m.group(1).replace(",", "§c§") + "}", marked)
    people = []
    for piece in SPLIT.split(protected):
        piece = piece.strip()
        if not piece:
            continue
        markers = []
        for group in MARKER_GROUP.findall(piece):
            markers += re.findall(r"\d+|[a-z]|[" + SYMBOL_MARKERS + "]", group.replace("§c§", ","))
        name = MARKER_GROUP.sub("", piece)
        sym = TRAILING_SYMBOLS.search(name)
        if sym:
            markers += [c for c in sym.group(0) if c in SYMBOL_MARKERS]
            name = name[: sym.start()]
        digits = re.search(r"(?<=[a-z])\s?(\d+(?:\s?,\s?\d+)*)$", name)   # "Smith1,2" without superscript
        if digits:
            markers += [d.strip() for d in digits.group(1).split(",")]
            name = name[: digits.start()]
        name = " ".join(name.replace("§c§", ",").split()).strip(" ,.")
        if name and DEGREE.match(name) and people:           # a degree: its markers belong to the name before it
            people[-1][1].extend(m.strip() for m in markers)
        elif name:
            people.append((name, [m.strip() for m in markers]))
    return people


def looks_like_author_line(marked: str) -> bool:
    people = split_people(marked)
    return bool(people) and sum(is_name(n) for n, _ in people) >= max(1, 0.7 * len(people))
