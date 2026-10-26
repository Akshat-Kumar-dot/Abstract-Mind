"""LaTeX source. Header fields come straight from the author commands of the
common document classes; the body becomes Blocks for declarations and counts."""
from __future__ import annotations

import re
from typing import Optional

from ..core.models import Block, Document
from ..core.text import collapse, find_emails

SYMBOLS = {"ast": "*", "dagger": "†", "ddagger": "‡", "star": "*", "S": "§", "P": "¶"}
OPEN, CLOSE = "\ue000", "\ue001"   # protect ^{...} markers while converting to text
BREAK = "\ue002"                    # a LaTeX \\ line break


# ---------------------------------------------------------------- low level

def strip_comments(s: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", s)


def read_group(s: str, i: int, open_ch: str = "{", close_ch: str = "}") -> tuple[str, int]:
    """s[i] must be open_ch. Returns (content, index after the closing char)."""
    depth = 0
    j = i
    while j < len(s):
        ch = s[j]
        if ch == "\\":
            j += 2
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def commands(s: str, name: str, nargs: int = 1) -> list[dict]:
    """Every \\name[opt]{arg}... in s, in order."""
    out = []
    for m in re.finditer(r"\\" + re.escape(name) + r"(?![A-Za-z])\*?", s):
        i = m.end()
        opt = None
        while i < len(s) and s[i] in " \t\n":
            i += 1
        if i < len(s) and s[i] == "[":
            opt, i = read_group(s, i, "[", "]")
        args = []
        for _ in range(nargs):
            while i < len(s) and s[i] in " \t\n":
                i += 1
            if i < len(s) and s[i] == "{":
                a, i = read_group(s, i)
                args.append(a)
        if len(args) == nargs:
            out.append({"start": m.start(), "end": i, "opt": opt, "args": args})
    return out


def remove_commands(s: str, name: str, nargs: int = 1) -> tuple[str, list[str]]:
    """Remove \\name{...}; returns the new string and the removed arguments."""
    found = commands(s, name, nargs)
    removed = []
    for c in reversed(found):
        removed.insert(0, c["args"][0] if c["args"] else "")
        s = s[:c["start"]] + s[c["end"]:]
    return s, removed


def split_top(s: str, sep: str) -> list[str]:
    """Split on a command like \\and, ignoring ones inside braces."""
    parts, depth, cur, i = [], 0, [], 0
    while i < len(s):
        if s.startswith(sep, i) and depth == 0 and not (i + len(sep) < len(s) and s[i + len(sep)].isalpha()):
            parts.append("".join(cur))
            cur = []
            i += len(sep)
            continue
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] in "{}":
            cur.append(s[i:i + 2])
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return [p for p in parts if p.strip()]


def mark(s: str) -> str:
    """Turn the many LaTeX superscript-marker spellings into protected markers."""
    s = re.sub(r"\\(?:inst|IEEEauthorrefmark|textsuperscript)\s*\{([^{}]*)\}", lambda m: OPEN + m.group(1) + CLOSE, s)
    s = re.sub(r"\$\s*\^\s*\{\s*\\(ast|dagger|ddagger|star|S|P)\s*\}\s*\$", lambda m: OPEN + SYMBOLS[m.group(1)] + CLOSE, s)
    s = re.sub(r"\$\s*\^\s*\\(ast|dagger|ddagger|star|S|P)\s*\$", lambda m: OPEN + SYMBOLS[m.group(1)] + CLOSE, s)
    s = re.sub(r"\$\s*\^\s*\{([^{}$]*)\}\s*\$", lambda m: OPEN + _sym(m.group(1)) + CLOSE, s)
    s = re.sub(r"\$\s*\^\s*([^\s${}])\s*\$", lambda m: OPEN + m.group(1) + CLOSE, s)
    return s


def _sym(s: str) -> str:
    return re.sub(r"\\(ast|dagger|ddagger|star|S|P)\b", lambda m: SYMBOLS[m.group(1)], s).replace(" ", "")


def to_text(s: str) -> str:
    s = mark(s)
    s = re.sub(r"\\\\(\[[^\]]*\])?", BREAK, s)   # only \\ ends a line; source newlines are spaces
    try:
        from pylatexenc.latex2text import LatexNodes2Text
        t = LatexNodes2Text(math_mode="verbatim", strict_latex_spaces=False).latex_to_text(s)
    except Exception:
        t = re.sub(r"\\[A-Za-z]+\*?(\[[^\]]*\])?", " ", s).replace("{", "").replace("}", "")
    t = t.replace(OPEN, "^{").replace(CLOSE, "}").replace("~", " ")
    t = re.sub(r"\s+", " ", t).replace(BREAK, "\n")
    return "\n".join(collapse(line) for line in t.split("\n") if line.strip())


def env(s: str, name: str) -> Optional[str]:
    """Content of the first \\begin{name}...\\end{name}. Plain string search, not
    a lazy regex: a file full of unclosed environments can't stall the server."""
    open_tag, close_tag = "\\begin{" + name + "}", "\\end{" + name + "}"
    i = s.find(open_tag)
    if i < 0:
        return None
    j = s.find(close_tag, i + len(open_tag))
    return s[i + len(open_tag):j] if j >= 0 else None


def strip_envs(s: str, names: tuple[str, ...]) -> str:
    """Remove every \\begin{name}...\\end{name} block (starred forms too) in one
    linear pass. An unclosed block is left as it is."""
    opener = re.compile(r"\\begin\{(" + "|".join(map(re.escape, names)) + r")(\*?)\}")
    out, i = [], 0
    while True:
        m = opener.search(s, i)
        if not m:
            break
        close_tag = "\\end{" + m.group(1) + m.group(2) + "}"
        j = s.find(close_tag, m.end())
        if j < 0:
            break
        out.append(s[i:m.start()])
        out.append(" ")
        i = j + len(close_tag)
    out.append(s[i:])
    return "".join(out)


# ---------------------------------------------------------------- header

def _author(name: str, markers: Optional[list[str]] = None) -> dict:
    return {"name": name, "markers": markers or [], "email": None, "orcid": None, "affiliations": [], "affiliation_parts": [], "corresponding": False}


def _names_with_markers(text: str) -> list[dict]:
    """'A^{1}, B^{2,*} and C' -> authors with markers."""
    text = re.sub(r"\b\d+\^\{(?:st|nd|rd|th)\}\s*", "", text)
    text = re.sub(r"\^\{([^}]*)\}", lambda m: "^{" + m.group(1).replace(",", "|") + "}", text)
    out = []
    for part in re.split(r",|;|\band\b|&|\n", text):
        markers = []
        for grp in re.findall(r"\^\{([^}]*)\}", part):
            markers += [x.strip() for x in grp.split("|") if x.strip()]
        name = collapse(re.sub(r"\^\{[^}]*\}", "", part))
        for sym in "*†‡§¶✉":
            if sym in name:
                markers.append(sym)
                name = name.replace(sym, "")
        name = collapse(name).strip(" .")
        if name:
            out.append(_author(name, markers))
        elif markers and out:
            out[-1]["markers"] += markers
    return out


def _kv(arg: str) -> dict:
    """organization={...}, city={...} as written by elsarticle."""
    out = {}
    for m in re.finditer(r"(\w+)\s*=\s*\{", arg):
        val, _ = read_group(arg, m.end() - 1)
        out[m.group(1).lower()] = to_text(val)
    return out


def _parts_text(parts: dict) -> str:
    keys = ["department", "institution", "organization", "addressline", "streetaddress", "city", "state", "postcode", "country"]
    return ", ".join(parts[k] for k in keys if parts.get(k))


def parse_header(src: str, cls: str) -> dict:
    start = src.find("\\begin{document}")
    end_m = re.search(r"\\section\*?\s*\{", src[max(start, 0):])
    region = src[: max(start, 0) + end_m.start()] if end_m else src
    h: dict = {"title": None, "short_title": None, "authors": [], "affiliation_map": {}, "emails": [], "footnotes": [], "abstract": None, "keywords": [], "family": None}

    titles = commands(region, "title")
    if titles:
        t = titles[0]
        raw, thanks = remove_commands(t["args"][0], "thanks")
        h["footnotes"] += [to_text(x) for x in thanks]
        h["title"] = collapse(to_text(raw).replace("\n", " "))
        if t["opt"]:
            h["short_title"] = collapse(to_text(t["opt"]))
    for name in ("titlerunning", "shorttitle", "runningtitle", "shortauthors"):
        c = commands(region, name)
        if c and name != "shortauthors":
            h["short_title"] = h["short_title"] or collapse(to_text(c[0]["args"][0]))

    if "\\IEEEauthorblockN" in region:
        h["family"] = "ieee"
        _ieee_blocks(region, h)
    elif cls in ("acmart",) or (cls.startswith("revtex") and "\\affiliation" in region):
        h["family"] = "acm/revtex"
        _sequential(region, h)
    elif "\\institute" in region and "\\at" in region:
        h["family"] = "svjour"
        _svjour(region, h)
    elif "\\institute" in region:
        h["family"] = "llncs"
        _llncs(region, h)
    elif cls == "elsarticle" or re.search(r"\\author\s*\[[^\]]+\]\s*\{", region) and ("\\address" in region or "\\affiliation" in region):
        h["family"] = "elsarticle"
        _elsarticle(region, h)
    elif "\\affil" in region:
        h["family"] = "authblk"
        _authblk(region, h)
    else:
        h["family"] = "generic"
        _generic(region, h)

    ab = env(src, "abstract")
    if ab is None:
        c = commands(src, "abstract")
        ab = c[0]["args"][0] if c else None
    if ab:
        h["abstract"] = collapse(to_text(ab).replace("\n", " "))

    kw = env(src, "IEEEkeywords") or env(src, "keyword") or env(src, "keywords")
    if kw is None:
        c = commands(src, "keywords")
        kw = c[0]["args"][0] if c else None
    if kw:
        kw = kw.replace("\\sep", ",").replace("\\and", ",")
        kw = re.sub(r"\\kwd\{([^}]*)\}", r"\1,", kw)
        h["keywords"] = [collapse(k).strip(" .") for k in re.split(r"[,;·]", to_text(kw).replace("\n", ",")) if collapse(k).strip(" .")]
    return h


def _ieee_blocks(region: str, h: dict) -> None:
    arg = commands(region, "author")
    if not arg:
        return
    a = arg[0]["args"][0]
    blocks = commands(a, "IEEEauthorblockN")
    affs = commands(a, "IEEEauthorblockA")
    for i, n in enumerate(blocks):
        names = _names_with_markers(to_text(n["args"][0]))
        nxt = blocks[i + 1]["start"] if i + 1 < len(blocks) else len(a)
        mine = [x for x in affs if n["end"] <= x["start"] < nxt]
        lines = []
        for x in mine:
            lines += to_text(x["args"][0]).split("\n")
        emails = []
        aff_lines = []
        for line in lines:
            es = find_emails(line)
            if es:
                emails += es
                continue
            aff_lines.append(re.sub(r"^\s*(e-?mail|email)\s*:?", "", line, flags=re.I).strip())
        marked = [ln for ln in aff_lines if ln.startswith("^{")]
        if marked:
            for ln in aff_lines:
                m = re.match(r"\^\{([^}]*)\}\s*(.*)", ln)
                if m:
                    h["affiliation_map"][m.group(1).strip()] = m.group(2).strip()
            h["emails"] += emails
        else:
            aff = ", ".join(x for x in aff_lines if x)
            for au in names:
                if aff:
                    au["affiliations"].append(aff)
            if len(names) == 1 and len(emails) == 1:
                names[0]["email"] = emails[0]
            else:
                h["emails"] += emails
        h["authors"] += names


def _sequential(region: str, h: dict) -> None:
    events = []
    for name in ("author", "affiliation", "email", "orcid", "authornote", "additionalaffiliation"):
        for c in commands(region, name):
            events.append((c["start"], name, c["args"][0]))
    events.sort()
    pending: list[dict] = []
    for _, name, arg in events:
        if name == "author":
            raw, thanks = remove_commands(arg, "thanks")
            h["footnotes"] += [to_text(x) for x in thanks]
            for au in _names_with_markers(to_text(raw)):
                if any("correspond" in to_text(x).lower() for x in thanks):
                    au["corresponding"] = True
                h["authors"].append(au)
                pending.append(au)
        elif not h["authors"]:
            continue
        elif name in ("affiliation", "additionalaffiliation"):
            parts = {}
            for key in ("department", "institution", "streetaddress", "city", "state", "postcode", "country"):
                c = commands(arg, key)
                if c:
                    parts[key] = to_text(c[0]["args"][0])
            text = _parts_text(parts) if parts else collapse(to_text(arg).replace("\n", ", "))
            for au in pending or [h["authors"][-1]]:
                au["affiliations"].append(text)
                if parts:
                    au["affiliation_parts"].append({"department": parts.get("department"), "institution": parts.get("institution"), "city": parts.get("city"), "country": parts.get("country")})
            pending = []
        elif name == "email":
            h["authors"][-1]["email"] = to_text(arg)
        elif name == "orcid":
            h["authors"][-1]["orcid"] = to_text(arg)
        elif name == "authornote" and "correspond" in to_text(arg).lower():
            h["authors"][-1]["corresponding"] = True


def _llncs(region: str, h: dict) -> None:
    a = commands(region, "author")
    if a:
        raw, thanks = remove_commands(a[0]["args"][0], "thanks")
        h["footnotes"] += [to_text(x) for x in thanks]
        for chunk in split_top(raw, "\\and"):
            orcid = None
            oc = commands(chunk, "orcidID")
            if oc:
                orcid = collapse(oc[0]["args"][0])
                chunk, _ = remove_commands(chunk, "orcidID")
            for au in _names_with_markers(to_text(chunk)):
                au["orcid"] = au["orcid"] or orcid
                h["authors"].append(au)
    inst = commands(region, "institute")
    if inst:
        for i, entry in enumerate(split_top(inst[0]["args"][0], "\\and"), start=1):
            entry, emails = remove_commands(entry, "email")
            entry, _ = remove_commands(entry, "url")
            for e in emails:
                h["emails"] += find_emails(to_text(e).replace(" ", "")) or [to_text(e)]
            text = collapse(to_text(entry).replace("\n", ", ")).strip(" ,")
            if text:
                h["affiliation_map"][str(i)] = text


def _elsarticle(region: str, h: dict) -> None:
    events = []
    for name in ("author", "ead", "cormark", "corref", "affiliation", "address"):
        for c in commands(region, name):
            events.append((c["start"], name, c))
    events.sort(key=lambda e: e[0])
    for _, name, c in events:
        arg = c["args"][0]
        if name == "author":
            raw = arg
            corr = "\\corref" in raw or "\\cormark" in raw
            raw = re.sub(r"\\(corref|fnref|cormark|fnmark)\s*(\[[^\]]*\])?(\{[^}]*\})?", "", raw)
            markers = [x.strip() for x in (c["opt"] or "").split(",") if x.strip()]
            for au in _names_with_markers(to_text(raw)):
                au["markers"] = markers + au["markers"]
                au["corresponding"] = corr
                h["authors"].append(au)
        elif not h["authors"] and name in ("ead", "cormark"):
            continue
        elif name == "ead" and (c["opt"] or "").lower() != "url":
            h["authors"][-1]["email"] = to_text(arg)
        elif name == "cormark":
            h["authors"][-1]["corresponding"] = True
        elif name in ("affiliation", "address"):
            parts = _kv(arg) if re.search(r"\w+\s*=\s*\{", arg) else {}
            text = _parts_text(parts) if parts else collapse(to_text(arg).replace("\n", ", "))
            label = (c["opt"] or str(len(h["affiliation_map"]) + 1)).strip()
            h["affiliation_map"][label] = text
            if parts:
                h.setdefault("affiliation_parts_map", {})[label] = {
                    "department": None, "institution": None, "city": parts.get("city"), "country": parts.get("country")}


def _svjour(region: str, h: dict) -> None:
    a = commands(region, "author")
    if a:
        raw, _ = remove_commands(a[0]["args"][0], "thanks")
        for chunk in split_top(raw, "\\and"):
            h["authors"] += _names_with_markers(to_text(chunk))
    inst = commands(region, "institute")
    if not inst:
        return
    for i, entry in enumerate(split_top(inst[0]["args"][0], "\\and")):
        entry, emails = remove_commands(entry, "email")
        who, _, addr = entry.partition("\\at")
        text = collapse(to_text(addr or who).replace("\n", ", ")).strip(" ,")
        who_name = collapse(to_text(who)) if addr else ""
        target = None
        for au in h["authors"]:
            if who_name and (au["name"].lower() in who_name.lower() or who_name.lower() in au["name"].lower()):
                target = au
        if target is None and i < len(h["authors"]):
            target = h["authors"][i]
        if target is not None and text:
            target["affiliations"].append(text)
            if emails:
                target["email"] = to_text(emails[0])


def _authblk(region: str, h: dict) -> None:
    for c in commands(region, "author"):
        markers = [x.strip() for x in (c["opt"] or "").split(",") if x.strip()]
        for au in _names_with_markers(to_text(c["args"][0])):
            au["markers"] = markers + au["markers"]
            h["authors"].append(au)
    for i, c in enumerate(commands(region, "affil"), start=1):
        h["affiliation_map"][(c["opt"] or str(i)).strip()] = collapse(to_text(c["args"][0]).replace("\n", ", "))


def _generic(region: str, h: dict) -> None:
    a = commands(region, "author")
    if not a:
        return
    raw, thanks = remove_commands(a[0]["args"][0], "thanks")
    h["footnotes"] += [to_text(x) for x in thanks]
    raw = re.sub(r"\\IEEEmembership\s*\{[^}]*\}", "", raw)
    for chunk in split_top(raw, "\\and"):
        lines = to_text(chunk).split("\n")
        if not lines:
            continue
        names = _names_with_markers(lines[0])
        emails, affs = [], []
        for line in lines[1:]:
            es = find_emails(line)
            if es:
                emails += es
                continue
            m = re.match(r"\^\{([^}]*)\}\s*(.*)", line)
            if m:
                h["affiliation_map"][m.group(1).strip()] = m.group(2).strip()
            elif line.strip():
                affs.append(line.strip())
        for au in names:
            if affs:
                au["affiliations"].append(", ".join(affs))
        if len(names) == 1 and len(emails) == 1:
            names[0]["email"] = emails[0]
        else:
            h["emails"] += emails
        h["authors"] += names


# ---------------------------------------------------------------- body

HEADING_CMDS = r"\\(?:section|subsection|subsubsection|paragraph|chapter)\*?\s*(?:\[[^\]]*\])?\s*\{"


def body_blocks(src: str) -> tuple[list[Block], dict]:
    b0 = src.find("\\begin{document}")
    body = src[b0 + len("\\begin{document}"):] if b0 >= 0 else src
    b1 = body.find("\\end{document}")
    body = body[:b1] if b1 >= 0 else body
    mt = body.find("\\maketitle")
    if mt >= 0:
        body = body[mt + len("\\maketitle"):]
    body = strip_envs(body, ("abstract", "IEEEkeywords", "keyword", "keywords", "frontmatter"))

    counts = {
        "figures": len(re.findall(r"\\begin\{(?:figure|SCfigure|wrapfigure)\*?\}", body)),
        "tables": len(re.findall(r"\\begin\{(?:table|sidewaystable)\*?\}", body)),
        "references": None,
        "references_note": None,
    }
    bib = env(body, "thebibliography")
    if bib is not None:
        counts["references"] = len(re.findall(r"\\bibitem\b", bib))
    else:
        keys = set()
        for c in re.finditer(r"\\(?:cite[a-zA-Z]*|parencite|textcite|autocite)\*?(?:\[[^\]]*\])*\{([^}]*)\}", body):
            keys.update(k.strip() for k in c.group(1).split(",") if k.strip())
        if keys:
            counts["references"] = len(keys)
            counts["references_note"] = "Counted from unique \\cite keys; the .bib file was not uploaded."

    body = strip_envs(body, ("figure", "table", "SCfigure", "wrapfigure", "sidewaystable", "thebibliography",
                             "equation", "align", "eqnarray", "gather", "multline", "tabular"))
    body = re.sub(r"\\begin\{acks?\}", lambda _: "\n\n\\section*{Acknowledgments}\n", body)
    body = re.sub(r"\\end\{acks?\}", "\n\n", body)
    body = re.sub(r"\\(bibliography|bibliographystyle|addbibresource|printbibliography|appendix|label|ref|cite[a-zA-Z]*)\*?(\[[^\]]*\])*(\{[^}]*\})?", " ", body)

    blocks: list[Block] = []
    pos = 0
    for m in re.finditer(HEADING_CMDS, body):
        blocks += _paras(body[pos:m.start()])
        title, end = read_group(body, m.end() - 1)
        t = collapse(to_text(title))
        if t:
            blocks.append(Block(text=t, marked=t, font_size=12, bold=True, style="heading"))
        pos = end
    blocks += _paras(body[pos:])
    return blocks, counts


def _paras(chunk: str) -> list[Block]:
    out = []
    for p in re.split(r"\n\s*\n", chunk):
        if not p.strip():
            continue
        t = collapse(to_text(p).replace("\n", " "))
        if t:
            out.append(Block(text=t, marked=t, font_size=10, style="body"))
    return out


def load_tex(data: bytes) -> Document:
    src = strip_comments(data.decode("utf-8", "replace"))
    m = re.search(r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", src)
    cls = m.group(1).strip() if m else "article"
    header = parse_header(src, cls)
    blocks, counts = body_blocks(src)
    header["counts"] = counts
    header["document_class"] = cls
    return Document(source="tex", blocks=blocks, tex=header)
