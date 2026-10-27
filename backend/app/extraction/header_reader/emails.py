"""Emails, and whose each one is.

Linked by the strongest evidence first; anything still unclear stays unlinked:
  block      inside the author's own block (IEEE conference, ACM, JMLR)
  statement  "A is with … (e-mail: a@x)"
  next to    printed beside or just under the name ("Correspondence: Name, email")
  symbol     "* a@x" belongs to the one author marked *
  name       the address spells the name (aarav.sharma@… -> Aarav Sharma), clearly better than anyone else's
  only       one author, one email
"""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

from .header import Person
from .layout import Line

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
GROUPED = re.compile(r"[{(\[]\s*([\w.+-]+(?:\s*[,;|]\s*[\w.+-]+)+)\s*[})\]]\s*@\s*([\w-]+(?:\.[\w-]+)+)")
SYMBOLS = "*∗⁎✉†‡§¶#"
ROLE = re.compile(r"^(permissions?|reprints?|editor(ial)?s?|office|info|support|contact|admin|copyright|help|"
                  r"no-?reply|journals?|submissions?|customerservice)@", re.I)


def find(lines: list[Line]) -> list[tuple[str, Line]]:
    """Every email address on these lines, in order, with grouped forms expanded."""
    out: list[tuple[str, Line]] = []
    for ln in lines:
        text = ln.text.replace(" @", "@").replace("@ ", "@")
        for g in GROUPED.finditer(text):
            out += [(f"{local.strip()}@{g.group(2)}".lower(), ln) for local in re.split(r"[,;|]", g.group(1))]
            text = text.replace(g.group(0), " ")
        out += [(e.lower().rstrip("."), ln) for e in EMAIL.findall(text)]
    seen, unique = set(), []
    for e, ln in out:
        if ROLE.match(e):                   # permissions@acm.org, editor@…: not an author's
            continue
        if e not in seen:
            seen.add(e)
            unique.append((e, ln))
    return unique


def _ascii(s: str) -> str:
    s = s.translate(str.maketrans({"ø": "o", "æ": "ae", "ß": "ss", "ł": "l", "đ": "d"}))
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def name_score(address: str, name: str) -> float:
    """How well an email's local part spells a name: 0-100."""
    local = re.sub(r"[^a-z]", "", _ascii(address.split("@")[0]))
    parts = [re.sub(r"[^a-z]", "", w) for w in _ascii(name).replace("-", " ").split()]
    parts = [w for w in parts if w]
    if not local or len(parts) < 2:
        return 0.0
    given, family = parts[0], parts[-1]
    initials = "".join(w[0] for w in parts[:-1])
    forms = [family, given, given + family, family + given, given[0] + family, family + given[0], initials + family,
             family + initials, given + family[0], "".join(parts), initials + family[0]]
    best = max(fuzz.ratio(local, f) for f in forms)
    if len(family) >= 4 and family in local:
        best = max(best, 85)
    return best


def link(people: list[Person], found: list[tuple[str, Line]], statements: list,
         lines: list[Line]) -> dict[str, tuple[str, str]]:
    """person name -> (email, how). `lines` are the pages' lines, to look above an email."""
    given: dict[str, tuple[str, str]] = {}
    taken: set[str] = set()
    if not people:
        return given

    def assign(person: Person, email: str, how: str) -> None:
        if person.name not in given and email not in taken:
            given[person.name] = (email, how)
            taken.add(email)

    def person_named(text: str, threshold: int = 90) -> Person | None:
        scores = [(fuzz.partial_ratio(_ascii(p.name), _ascii(text)), p) for p in people if len(text) >= 4]
        scores.sort(key=lambda x: -x[0])
        if scores and scores[0][0] >= threshold and (len(scores) == 1 or scores[1][0] < scores[0][0]):
            return scores[0][1]
        return None

    # block: emails printed inside an author's own block
    for p in people:
        mine = [e for e, ln in found if ln in p.block]
        if len(mine) == 1:
            assign(p, mine[0], "in the author's block")
        for e in mine if len(mine) > 1 else []:
            if name_score(e, p.name) >= 70:
                assign(p, e, "in the author's block")

    # statement: "A and B are with … (e-mail: a@x; b@y)"
    for names, _, emails in statements:
        group = [q for n in names for q in [person_named(n, 85)] if q]
        if len(group) == 1 and len(emails) == 1:
            assign(group[0], emails[0], "in the author's 'is with' note")
        else:
            for e in emails:
                best = max(group, key=lambda q: name_score(e, q.name), default=None)
                if best and name_score(e, best.name) >= 70:
                    assign(best, e, "in the author's 'is with' note")

    # Elsevier: "E-mail addresses: a@x (A. Smith), b@y (B. Lee)" - the name in brackets after the email
    for e, ln in found:
        after = ln.text.lower().split(e, 1)[1] if e in ln.text.lower() else ""
        named = re.match(r"\s*\(([^)@]{3,60})\)", ln.text[len(ln.text) - len(after):]) if after else None
        p = person_named(named.group(1), 85) if named else None
        if named and not p:                     # "(A. Smith)": the one author whose family name is Smith
            family = _ascii(named.group(1).split()[-1]).strip(".,")
            same = [q for q in people if _ascii(q.name.split()[-1]) == family]
            p = same[0] if len(same) == 1 else None
        if p:
            assign(p, e, "name in brackets after the email")

    # next to: the name on the same line before the email, or on one of the two lines above.
    # A line holding another email is someone else's, and the name must be most of the line.
    for e, ln in found:
        if e in taken or e not in ln.text.lower().replace(" ", ""):     # "{alice,carol}@x" names nobody
            continue
        local = e.split("@")[0]
        before = ln.text[: ln.text.lower().find(local)] if local in ln.text.lower() else ""
        candidates = [before] + [x.text for x in _lines_above(ln, lines, 2) if "@" not in x.text]
        candidates += [c.split(",")[0] for c in candidates if "," in c]
        for text in candidates:
            text = re.sub(r"(?i)^\W*(correspond\w*( author)?|e-?mail( address)?)\W*", "", text).strip(" ,:;*")
            p = person_named(text) if text and len(text) <= 2 * max(len(q.name) for q in people) else None
            if p:
                assign(p, e, "printed next to the name")
                break

    # symbol: "* a@x" -> the one author marked *
    for e, ln in found:
        lead = ln.text.strip()[:1]
        if e not in taken and lead in SYMBOLS:
            marked = [p for p in people if lead in p.markers or (lead in "*∗⁎" and any(m in "*∗⁎" for m in p.markers))]
            if len(marked) == 1:
                assign(marked[0], e, f"marked {lead} like the author")

    # name: the address spells the name, and clearly better than anyone else's
    for e, _ in found:
        if e in taken:
            continue
        ranked = sorted(((name_score(e, p.name), p) for p in people if p.name not in given), key=lambda x: -x[0])
        if ranked and ranked[0][0] >= 80 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 10):
            assign(ranked[0][1], e, "the address matches the name")

    # only: one author, one email
    left = [e for e, _ in found if e not in taken]
    if len(people) == 1 and len(left) == 1 and not given:
        assign(people[0], left[0], "the only author and the only email")
    return given


def _lines_above(ln: Line, lines: list[Line], n: int) -> list[Line]:
    """The n lines just above ln, in its column."""
    above = [x for x in lines if x.page == ln.page and x.y1 <= ln.y0 + 1 and abs(x.x0 - ln.x0) < 40 and ln.y0 - x.y1 < 3 * ln.height]
    return sorted(above, key=lambda x: -x.y0)[:n]
