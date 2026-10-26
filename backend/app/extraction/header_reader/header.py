"""Title and authors.

  title    the largest text on page 1 (all its lines, even when a sidebar is
           printed between them)
  authors  name lines directly under the title, in the title's column. Two
           layouts:
             list   "A^{1}, B^{1,2} and C^{2}" (possibly wrapped over lines)
             blocks one name per block, its affiliation and email underneath
                    (IEEE conference, ACM, JMLR, plain preprints)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .layout import Line
from .names import is_name, looks_like_author_line, split_people

STOP = re.compile(r"^\s*(abstract|summary|a\s?b\s?s\s?t\s?r\s?a\s?c\s?t|keywords?|index terms|introduction|"
                  r"background|objectives?|purpose|highlights|article info|a r t i c l e|edited by|received|accepted|revised|published|"
                  r"citation|open access|significance)\b", re.I)
DATES = re.compile(r"^\s*(received|accepted|revised|published)\b", re.I)    # a dates sidebar, never the end of the header
MARKER_TEXT = re.compile(r"^(?:\^\{[^}]*\}|[\s,*†‡§¶∗⁎#✉\d])+$")


@dataclass
class Person:
    name: str
    markers: list[str]
    line: Line                                  # where the name was printed
    block: list[Line] = field(default_factory=list)   # in block layout: the lines under the name
    rows: list[Line] = field(default_factory=list)    # in list layout: every line of the author list
    inline_place: str = ""                             # in inline layout: the place printed after the name


def find_title(lines: list[Line]) -> list[Line]:
    """Lines in the largest size that has at least three words; the top part of page 1 only."""
    if not lines:
        return []
    page_bottom = max(ln.y1 for ln in lines)
    upper = [ln for ln in lines if ln.y0 < 0.6 * page_bottom]
    for size in sorted({round(ln.size * 2) / 2 for ln in upper}, reverse=True):
        rows = [ln for ln in upper if abs(ln.size - size) <= 0.6]
        # the title is one stack of lines (a big gap starts another: a journal name above it is a stack of its own)
        stacks: list[list[Line]] = []
        for ln in rows:
            if stacks and ln.y0 - stacks[-1][-1].y1 <= 2.5 * stacks[-1][0].height:
                stacks[-1].append(ln)
            else:
                stacks.append([ln])
        for stack in stacks:
            if len(" ".join(ln.text for ln in stack).split()) >= 3:
                return stack
    return []


def _in_column(ln: Line, left: float, right: float) -> bool:
    centre = (ln.x0 + ln.x1) / 2
    return left - 5 <= centre <= right + 5 or (ln.x0 >= left - 5 and ln.x0 < right)


def region_under(title: list[Line], lines: list[Line]) -> list[Line]:
    """Lines below the title, in its column, up to the abstract (or a long paragraph)."""
    left, right = min(t.x0 for t in title), max(t.x1 for t in title)
    bottom = title[-1].y1
    out: list[Line] = []
    for ln in lines:
        if ln.page != title[0].page or ln.y0 < bottom - 1 or ln in title:
            continue
        # in the title's column, or the tail of a line already taken (markers printed past the title's edge)
        tail = out and abs(ln.y0 - out[-1].y0) < out[-1].height and 0 <= ln.x0 - out[-1].x1 < 60
        if not (_in_column(ln, left, right) or tail):
            continue
        if ln.y0 - bottom > 260:
            break
        if DATES.match(ln.text) and len(ln.text) < 60:
            continue
        if STOP.match(ln.text):
            # "Abstract" under the authors ends the header; a sidebar item off to the side
            # ("Received: 23 July 2025" next to Nature's author list) is just skipped
            if out and (ln.x1 < min(o.x0 for o in out) or ln.x0 > max(o.x1 for o in out)):
                continue
            break
        out.append(ln)
    return out


def _attach_loose_markers(lines: list[Line]) -> list[Line]:
    """Marker-only fragments on a name's row ("1", "^{1,2}*") belong to that row.
    Printed after the line's end they are its last name's markers; printed
    inside it (Cureus) they are kept apart, to be handed out by position."""
    out: list[Line] = []
    for ln in lines:
        if out and MARKER_TEXT.match(ln.marked.strip()) and abs(ln.y0 - out[-1].y0) < out[-1].height:
            prev = out[-1]
            markers = ln.marked if ln.marked.startswith("^{") else "^{" + ln.text.replace(" ", "") + "}"
            if ln.x0 >= prev.x1 - 3:
                prev.marked += markers
                prev.x1 = ln.x1
            else:
                prev.loose.append((ln.x0, markers))
            continue
        out.append(ln)
    return out


INLINE = re.compile(r"^([A-Z][A-Z\-'’. ]+[A-Z])\s*,\s*(.+)$")    # "MICHAEL THOMPSON, University of Oxford, UK"


def find_authors(region: list[Line]) -> tuple[list[Person], str]:
    """People under the title, in printed order, and the layout ("list", "blocks" or "inline")."""
    region = _attach_loose_markers(region)

    # Inline layout (ACM journals): one author per line, name in capitals, then the place.
    inline = [(ln, INLINE.match(ln.text)) for ln in region]
    inline = [(ln, m) for ln, m in inline if m and is_name(m.group(1)) and not is_name(m.group(2).split(",")[0])]
    if len(inline) >= 1 and inline[0][0] is region[0]:
        people = [Person(m.group(1).title(), [], line=ln, block=[]) for ln, m in inline]
        for p, (_, m) in zip(people, inline):
            p.inline_place = m.group(2).strip()
        return people, "inline"

    names = [ln for ln in region if "@" not in ln.text and looks_like_author_line(ln.marked)]
    if not names:
        return [], "none"

    # Block layout: name lines holding one person each, with non-name lines under them.
    # names are printed larger than the place lines under them ("Murray Hill" under a name is a place)
    if len({round(ln.size) for ln in names}) > 1 and all(len(split_people(ln.marked)) == 1 for ln in names):
        names = [ln for ln in names if ln.size >= max(n.size for n in names) - 0.5]
    singles = [ln for ln in names if len(split_people(ln.marked)) == 1]
    under = [ln for ln in region if ln not in names]
    if len(singles) == len(names) and under and not any(m for ln in names for _, m in split_people(ln.marked)):
        people = []
        for ln in sorted(names, key=lambda l: (round(l.y0 / 4), l.x0)):
            people.append(Person(*split_people(ln.marked)[0], line=ln))
        for ln in under:                       # each line goes to the nearest name above it in its column
            above = [p for p in people if p.line.y0 < ln.y0 and _in_column(ln, p.line.x0 - 30, p.line.x1 + 30)]
            if above:
                max(above, key=lambda p: p.line.y0).block.append(ln)
        return people, "blocks"

    # List layout: consecutive name lines, joined (a name can wrap onto the next line).
    first = region.index(names[0])
    joined, used = [], []
    for ln in region[first:]:
        if used and (ln.x1 < used[0].x0 or ln.x0 > used[0].x1):   # a sidebar line beside the list ("Accepted: …")
            continue
        if ln in names or (used and ln.y0 - used[-1].y1 < 0.8 * ln.height and not STOP.match(ln.text) and
                           "@" not in ln.text and len(ln.text) < 40 and is_name(" ".join(ln.text.split()[:3]))):
            joined.append(ln.marked)
            used.append(ln)
        elif used:
            break
    people = [Person(name, markers, line=used[0], rows=used) for name, markers in split_people(" ".join(joined))]
    people = [p for p in people if is_name(p.name)]
    _markers_by_position(people, used)
    return people, "list"


def _markers_by_position(people: list[Person], used: list[Line]) -> None:
    """Cureus-style: markers printed as separate tiny numbers in the gaps after
    each name. If the line has no markers but the right number of loose ones,
    give them out in order."""
    for ln in used:                            # line by line: a list can wrap onto a second line
        loose = [re.sub(r"[\^{}]", "", m) for _, m in sorted(ln.loose)]
        on_line = [n for n, _ in split_people(ln.marked) if is_name(n)]
        mine = [p for p in people if p.name in on_line and not p.markers]
        if loose and len(loose) == len(mine):
            for p, m in zip(mine, loose):
                p.markers = re.findall(r"\d+|[a-z]|[*†‡§¶∗⁎#✉]", m)
