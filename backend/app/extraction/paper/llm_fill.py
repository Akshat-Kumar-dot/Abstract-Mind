"""LLM gap filling. Called only when the rules left something required missing or
uncertain. It sees only the header and page-1 footnotes, and every value it
returns must be found in that text, or it is dropped."""
from __future__ import annotations

from typing import Optional

from rapidfuzz import fuzz

from ..core.models import Block
from ..core.text import normalize
from ..core.verify import email_ok, grounded, orcid_ok
from ..llm import client
from ..llm.schemas import INSTRUCTIONS, PAPER_HEADER
from .authors import THRESHOLD
from .header import Author, Header, Line
from .zones import Zones


def reasons(h: Header) -> list[str]:
    out = []
    if not h.title:
        out.append("title not found")
    if not h.authors and not h.double_blind:
        out.append("no authors found")
    elif any(not a.affiliations for a in h.authors):
        out.append("some authors have no affiliation")
    elif any(a.score < THRESHOLD for a in h.authors):
        out.append("some authors are uncertain")
    return out


def header_text(z: Zones) -> str:
    text = "\n".join(b.marked for b in z.header)
    if z.footnotes:
        text += "\n--- page 1 footnotes ---\n" + "\n".join(b.marked for b in z.footnotes)
    return text[:8000]


def fill(h: Header, z: Zones, keywords: list[str], allow_ai: bool = False) -> tuple[dict, list[str]]:
    """Returns (llm info for the result, keywords possibly filled). Nothing is
    sent to a provider unless the person allowed it for this upload."""
    provider = client.provider()
    why = reasons(h)
    info = {"provider": provider if allow_ai else None, "used": False, "reason": None}
    if not allow_ai:
        if why and provider:
            info["reason"] = "Rules only. Ticking \"Let AI help\" may fill the gaps; it sends the page-1 header text to the AI provider."
        return info, keywords
    if provider is None:
        info["reason"] = "AI help isn't set up on this server; rules only." if why else None
        return info, keywords
    if not why:
        info["reason"] = "Not needed: the rules found every required field."
        return info, keywords
    text = header_text(z)
    try:
        data = client.extract_json(INSTRUCTIONS, "Manuscript header:\n" + text, PAPER_HEADER)
    except client.LLMError as e:
        info["reason"] = f"LLM call failed ({e}); rules only."
        return info, keywords
    info["used"] = True
    info["reason"] = "Called because " + ", ".join(why) + "."
    hay = normalize(text.replace("^{", " ").replace("}", " "))
    dropped = 0

    title = (data.get("title") or "").strip()
    if title and not h.title:
        if grounded(title, hay):
            h.title, h.title_source = title, "llm"
        else:
            dropped += 1

    llm_authors = []
    for x in data.get("authors") or []:
        name = (x.get("name") or "").strip()
        if not name:
            continue
        if not grounded(name, hay):
            dropped += 1
            continue
        llm_authors.append(x)

    def clean(x: dict) -> tuple[Optional[str], Optional[str], list[str]]:
        email = (x.get("email") or "").strip()
        email = email if email and email_ok(email) and grounded(email, hay) else None
        orcid = (x.get("orcid") or "").strip()
        orcid = orcid if orcid and orcid_ok(orcid) else None
        affs = [a.strip() for a in x.get("affiliations") or [] if a and a.strip() and grounded(a.strip(), hay, 85)]
        return email, orcid, affs

    if not h.authors:
        for x in llm_authors:
            email, orcid, affs = clean(x)
            line = Line(block=Block(text=x["name"], marked=x["name"], page=1), kind="llm", index=-1)
            a = Author(name=x["name"].strip(), markers=[], line=line, email=email, orcid=orcid, affiliations=affs, source="llm")
            a.email_how = "LLM" if email else None
            a.link_mode = "LLM" if affs else None
            if x.get("corresponding"):
                a.corresponding, a.corresponding_how = True, "LLM"
            h.authors.append(a)
    else:
        matched = set()
        for a in h.authors:
            best = max(llm_authors, key=lambda x: fuzz.token_sort_ratio(a.name, x["name"]), default=None)
            if best is None or fuzz.token_sort_ratio(a.name, best["name"]) < 85:
                a.failed += 1
                a.note = "The LLM did not list this name as an author."
                continue
            matched.add(id(best))
            a.agreed = True
            email, orcid, affs = clean(best)
            if not a.email and email:
                a.email, a.email_how = email, "LLM"
            if not a.orcid and orcid:
                a.orcid = orcid
            if not a.affiliations and affs:
                a.affiliations, a.link_mode = affs, "LLM"
        if not any(a.corresponding for a in h.authors):
            for a in h.authors:
                best = next((x for x in llm_authors if fuzz.token_sort_ratio(a.name, x["name"]) >= 85), None)
                if best and best.get("corresponding"):
                    a.corresponding, a.corresponding_how = True, "LLM"
        for x in llm_authors:
            if id(x) in matched:
                continue
            email, orcid, affs = clean(x)
            line = Line(block=Block(text=x["name"], marked=x["name"], page=1), kind="llm", index=-1)
            h.authors.append(Author(name=x["name"].strip(), markers=[], line=line, email=email, orcid=orcid, affiliations=affs,
                                    source="suggested", note="Found only by the LLM; check that this person is an author."))

    if not keywords:
        kws = [k.strip() for k in data.get("keywords") or [] if k and k.strip()]
        keywords = [k for k in kws if grounded(k, hay)]
    if dropped:
        info["reason"] += f" {dropped} value(s) were dropped because they are not in the paper."
    return info, keywords
