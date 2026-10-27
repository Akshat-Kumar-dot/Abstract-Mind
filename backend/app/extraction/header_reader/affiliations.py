"""Affiliations, and which author each belongs to.

    markers     "^{1}Dept…, ^{2}Lab…" or "1 Dept…, 2 Lab…" read in order 1, 2, 3 (or a, b, c),
                so a number inside an address ("Kunming 650221") is never taken for a marker
    blocks      the lines under each author's name (IEEE conference, ACM, JMLR, preprints)
    statements  IEEE Transactions footnote: "A and B are with the Department of …"
    single      no markers, one affiliation: everyone has it

Several affiliations with no way to tell who belongs where are not guessed:
they are returned unlinked, and a check says so.
"""
from __future__ import annotations

import re

from .header import Person
from .layout import Line
from .names import looks_like_author_line

# a marker: superscript "^{1}", or "1 Dept" / "a Dept" / "(1) Dept" after a comma or at the start,
# or "1. Dept" anywhere (Cureus: "…Lucknow, IND 2. Department…")
MARK = re.compile(r"(?:^|(?<=\s))([†‡§¶#])\s?(?=[A-ZÀ-ɏ])|\^\{([^}]+)\}|(?:^|(?<=[,;.]\s)|(?<=\s\s))\(?(\d{1,2}|[a-z])\)?\s?(?=[A-ZÀ-ɏ])"
                  r"|(?:^|(?<=\s))(\d{1,2})\.\s(?=[A-ZÀ-ɏ])")
FOOTNOTE = re.compile(r"^\W*(these authors|contributed equally|equal contribution|correspond|to whom|present address|"
                      r"deceased|e-?mail|current address)", re.I)
END_OF_LIST = re.compile(r"^\s*(\*|∗|†|‡|correspond|e-?mail|abstract|received|keywords|these authors|present address|"
                         r"©|doi|https?://|a b s t r a c t|edited by|citation|open access)", re.I)
HEADING = re.compile(r"^\s*\(?\d{1,2}\)?\.?\s+(introduction|background|related work|methods?|materials|results|discussion|"
                     r"conclusions?|overview|preliminaries|motivation)\b", re.I)          # "1 Introduction" is a section
REFERENCES = re.compile(r"^\s*(\d+\.?\s*)?(references|bibliography|literature cited)\s*$", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _sequences(markers: list[str]) -> list[list[str]]:
    """Numbers and letters are tried as separate lists: in "Smith^{a,b,1}" the
    letters are affiliations and the 1 is a footnote (or the other way round)."""
    digits = sorted({m for m in markers if m.isdigit()}, key=int)
    letters = sorted({m for m in markers if m.isalpha()})
    symbols = sorted({m for m in markers if m in "†‡§¶#"}, key="†‡§¶#".index)    # ACS: † and ‡ label places
    return [s for s in (digits, letters, symbols) if s]


def _join(lines: list[Line]) -> str:
    text = ""
    for ln in lines:
        part = ln.marked
        if text.endswith("-") and part[:1].islower():
            text = text[:-1] + part
        else:
            text = (text + ("  " if MARK.match(part) else " ") + part).strip()
    return text


def _paragraph(lines: list[Line], start: int) -> list[Line]:
    """The start line and the lines that continue it (same column, same size, close below)."""
    first = lines[start]
    out = [first]
    for ln in lines[start + 1:]:
        prev = out[-1]
        if ln.page != first.page or ln.y0 < prev.y0:
            continue
        centred = abs((ln.x0 + ln.x1) / 2 - (first.x0 + first.x1) / 2) < 30      # LNCS centres each line
        same_column = first.x0 - 8 <= ln.x0 <= first.x0 + 60 or centred
        if not same_column:
            continue
        next_entry = MARK.match(ln.marked) and MARK.match(first.marked)     # "‡Dept" after "†Dept" is the next entry, not a note
        if ln.y0 - prev.y1 > 1.8 * prev.height or abs(ln.size - first.size) > 1.2 or (END_OF_LIST.match(ln.text) and not next_entry):
            break
        out.append(ln)
    return out


def _split_by_markers(text: str, expected: list[str]) -> tuple[dict[str, str], str]:
    """'^{1}A, ^{2}B' -> ({'1': 'A', '2': 'B'}, text before the first marker)."""
    found, want = [], list(expected)
    for m in MARK.finditer(text):
        value = (m.group(1) or m.group(2) or m.group(3) or m.group(4) or "").strip(" ,")
        for v in [x for x in re.split(r"\s*,\s*", value) if x]:
            if want and v == want[0]:
                found.append((m.start(), m.end(), v))
                want.pop(0)
    entries, footnotes, before = {}, {}, text[: found[0][0]] if found else ""
    for i, (s, e, v) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(text)
        entry = _clean(text[e:end])
        # "^{4}These authors contributed equally" is a footnote, not a place
        (footnotes if FOOTNOTE.match(entry) else entries)[v] = entry
    return entries, footnotes, _clean(before)


def _clean(text: str) -> str:
    text = re.sub(r"\^\{[^}]*\}", "", text)
    text = re.sub(r"(?i)^\W*(author\s+)?affiliations?\s*:", "", text)          # the label, not a place
    text = EMAIL.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;.")
    text = re.sub(r"(?:\s+and|\s*&)$", "", text)          # a trailing "and", not the end of "Switzerland"
    return text


def by_markers(people: list[Person], pages: list[list[Line]]) -> tuple[dict[str, str], dict[str, str], str, str]:
    """marker -> affiliation text; marker -> footnote text ("contributed equally");
    an unmarked affiliation printed before the marked ones (it belongs to authors
    without markers); and where it was found."""
    best: dict[str, str] = {}
    notes: dict[str, str] = {}
    unmarked = where = ""
    author_rows = {id(ln) for p in people for ln in (p.rows or [p.line])}
    for expected in _sequences([m for p in people for m in p.markers]):
        entries, footnotes, before, place = _search(expected, pages, author_rows)
        notes.update(footnotes)
        if len(entries) > len(best):
            best, unmarked, where = entries, before, place
    return best, notes, unmarked, where


def _search(expected: list[str], pages: list[list[Line]], author_rows: set[int]) -> tuple[dict[str, str], dict[str, str], str, str]:
    """The paragraph holding the most of the expected markers, in order."""
    first_mark = re.compile(r"\^\{\s*" + re.escape(expected[0]) + r"\s*[,}]|^\s*\(?" + re.escape(expected[0]) +
                            r"\)?\.?\s?(?=[A-ZÀ-ɏ])")
    best: dict[str, str] = {}
    notes: dict[str, str] = {}
    unmarked = where = ""
    for lines in pages:
        for i, ln in enumerate(lines):
            if REFERENCES.match(ln.text):                  # numbered references are not an affiliation list
                break
            if HEADING.match(ln.text):
                continue
            if not first_mark.search(ln.marked):          # the list may start mid-line, after an unmarked affiliation
                continue
            if id(ln) in author_rows or looks_like_author_line(ln.marked):   # the author lines carry the same markers
                continue
            para = _paragraph(lines, i)
            entries, footnotes, before = _split_by_markers(_join(para), expected)
            if len(entries) + len(footnotes) > len(best) + len(notes):
                best, notes, where = entries, footnotes, f"page {ln.page}"
                unmarked = _with_lines_above(before, lines, i)
            if len(best) + len(notes) == len(expected):
                return best, notes, unmarked, where
    return best, notes, unmarked, where


def _with_lines_above(before: str, lines: list[Line], i: int) -> str:
    """An unmarked affiliation printed before the marked list can begin on the
    line(s) above it: 'Department of Ophthalmology, Dr. D. Y. Patil Medical College' /
    'and Hospitals, Pune, Maharashtra, ^{1}Department of …'."""
    start, text = lines[i], before
    for k in range(i - 1, max(i - 3, -1), -1):
        above, below = lines[k], lines[k + 1]
        if (abs(above.size - start.size) > 0.6 or below.y0 - above.y1 > 1.5 * start.height or abs(above.x0 - start.x0) > 60
                or "@" in above.text or END_OF_LIST.match(above.text) or MARK.search(above.marked)
                or looks_like_author_line(above.marked)):
            break
        text = _clean(above.marked) + (" " + text if text else "")
    return _clean(text)


ADDRESS_NOTE = re.compile(r"^\s*authors?['’]?\s*(?:current\s+)?address(?:es)?\s*:\s*", re.I)


def address_note(lines: list[Line]) -> list[tuple[str, str, list[str]]]:
    """ACM: "Authors' addresses: A. Name, a@x, Dept…, City, Country; B. Name, …"
    -> [(name, address, [emails])], one per author."""
    for i, ln in enumerate(lines):
        if not ADDRESS_NOTE.match(ln.text):
            continue
        para = [ln]
        for nxt in lines[i + 1:]:
            if nxt.page != ln.page or nxt.y0 - para[-1].y1 > 1.5 * ln.height or abs(nxt.size - ln.size) > 0.6:
                break
            para.append(nxt)
        text = ADDRESS_NOTE.sub("", " ".join(x.text for x in para))
        out = []
        for part in re.split(r";\s*", text):
            emails = [e.lower() for e in EMAIL.findall(part)]
            pieces = [p.strip() for p in EMAIL.sub("", part).split(",") if p.strip()]
            if len(pieces) >= 2:
                out.append((pieces[0], _clean(", ".join(pieces[1:])), emails))
        return out
    return []


EMAIL_LABEL = re.compile(r"^\s*e-?mail(?:\s+address(?:es)?)?\s*:", re.I)


def end_addresses(lines: list[Line]) -> list[tuple[str, str]]:
    """AMS style: at the end of the paper, each author's address followed by
    'Email address: …', in the same order as the authors. -> [(address, email)]"""
    out, previous = [], -1
    for i, ln in enumerate(lines):
        email = EMAIL.search(ln.text)
        if not (EMAIL_LABEL.match(ln.text) and email):
            continue
        block, j = [], i - 1
        while j > previous and lines[j].page == ln.page and (block[-1] if block else ln).y0 - lines[j].y1 < 2 * ln.height:
            block.append(lines[j])
            j -= 1
        out.append((_clean(_join(list(reversed(block)))), email.group(0).lower()))
        previous = i
    return out


def by_blocks(people: list[Person]) -> dict[str, str]:
    """name -> the non-email lines of its block, joined."""
    out = {}
    for p in people:
        rows = [ln.text.strip(" ,;") for ln in p.block if not EMAIL.search(ln.text) and not END_OF_LIST.match(ln.text)]
        if rows:
            out[p.name] = _clean(", ".join(rows))
    return out


IS_WITH = re.compile(r"\s(?:is|are)\s+(?:now\s+)?with\s+(?:the\s+)?")


def by_statements(lines: list[Line]) -> list[tuple[list[str], str, list[str]]]:
    """'A and B are with the Dept of X, Univ, City (e-mail: a@x; b@x).' -> ([A, B], aff, [emails]).
    A plain scan around each "is with" / "are with" (no nested patterns, so it stays fast on long pages)."""
    text = " ".join(ln.text for ln in lines)
    out = []
    for m in IS_WITH.finditer(text):
        before = text[max(0, m.start() - 160): m.start()]
        before = re.split(r"[.;:)]\s", before)[-1]                       # back to the previous sentence
        names = [n.strip() for n in re.split(r",\s*(?:and\s+)?|\s+and\s+", before) if n.strip()]
        names = [n for n in names if 2 <= len(n.split()) <= 5 and n[0].isupper()]
        after = text[m.end(): m.end() + 400]
        place, _, rest = after.partition("(")
        place = re.split(r"\.\s+[A-Z]|\.$", place)[0]
        emails = EMAIL.findall(rest.split(")")[0]) if rest else []
        if names:
            out.append((names, _clean(place), [e.lower() for e in emails]))
    return out


def unmarked_entries(region: list[Line], last_author_line: Line) -> list[str]:
    """Affiliation lines printed under the author list without markers."""
    rows = []
    for ln in region:
        if ln.y0 <= last_author_line.y0 + 1 or "@" in ln.text:
            continue
        if END_OF_LIST.match(ln.text):
            break
        rows.append(ln)
    entries, current, prev = [], [], None
    for ln in rows:
        if prev and ln.y0 - prev.y1 > 1.2 * prev.height and current:
            entries.append(_clean(" ".join(current)))
            current = []
        current.append(ln.text)
        prev = ln
    if current:
        entries.append(_clean(" ".join(current)))
    return [e for e in entries if len(e) > 6]
