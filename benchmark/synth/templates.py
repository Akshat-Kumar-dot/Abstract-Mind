"""Journal and conference formats, filled with made-up authors.

Each style writes the author block the way that publisher's official LaTeX
class does (the same classes Overleaf's template gallery uses), then the same
short body: abstract, keywords, a section, and a reference list full of other
people's names (which must never be read as authors).

STYLES[name] = (render function, what the format shows):
  corresponding  the format marks a corresponding author
  emails         "all", "corresponding" (only that author's) or "none"
"""
from __future__ import annotations

from people import Paper

ACCENTS = {"é": r"\'e", "É": r"\'E", "á": r"\'a", "í": r"\'i", "ó": r"\'o", "à": r"\`a", "ã": r"\~a", "ä": r"\"a",
           "ë": r"\"e", "ö": r"\"o", "ü": r"\"u", "ø": r"{\o}", "ç": r"\c{c}"}


def tex(s: str) -> str:
    """Plain text -> LaTeX: accents as commands (works with every class), specials escaped."""
    s = s.replace("\\", "").replace("&", r"\&").replace("_", r"\_").replace("%", r"\%").replace("#", r"\#")
    for ch, cmd in ACCENTS.items():
        s = s.replace(ch, "{" + cmd + "}")
    return s


ABSTRACT = ("We study the problem described in the title and propose a simple method that runs on commodity "
            "hardware. Experiments on three public datasets show consistent gains over strong baselines, and an "
            "ablation explains where the improvements come from.")
KEYWORDS = ["deep learning", "edge computing", "benchmark"]
BODY = r"""
\section{Introduction}
Prior work by Kumar and Lee~\cite{r1} and by Zhang \emph{et al.}~\cite{r2} studied related settings. Our method differs
in two ways. First, it needs no labelled data. Second, it runs on a single CPU core in real time.

\section{Method}
We describe the model, the training objective and the evaluation protocol. All code will be released.
"""
REFS = r"""
\begin{thebibliography}{9}
\bibitem{r1} A. Kumar and S.-H. Lee, ``Learning without labels,'' \emph{Journal of Machine Learning Research}, vol. 21, pp. 1--30, 2020.
\bibitem{r2} H. Zhang, M. Rossi, and P. O'Neil, ``Efficient inference on the edge,'' in \emph{Proc. CVPR}, 2021, pp. 100--109.
\bibitem{r3} R. Gupta, ``A survey of federated learning,'' \emph{ACM Computing Surveys}, vol. 54, no. 2, 2022.
\end{thebibliography}
"""


def _doc(preamble: str, front: str, *, abstract_after_front: bool = True, end: str = "") -> str:
    abstract = r"\begin{abstract}" + ABSTRACT + r"\end{abstract}"
    head = (front + "\n" + abstract) if abstract_after_front else (abstract + "\n" + front)
    return f"{preamble}\n\\begin{{document}}\n{head}\n{BODY}\n{REFS}\n{end}\n\\end{{document}}\n"


def _marks(p: Paper, a) -> str:
    return ",".join(f.id for f in a.affiliations)


def _aff_lines(f) -> str:
    return f"{tex(f.department)}, {tex(f.institution)}, {tex(f.city)}, {tex(f.country)}"


# ------------------------------------------------------------ IEEE
def ieee_conference(p: Paper) -> str:
    blocks = []
    for a in p.authors:
        lines = [r"\textit{" + tex(f.department) + r"} \\ " + tex(f.institution) + r" \\ " + tex(f.city) + ", " + tex(f.country)
                 for f in a.affiliations]
        if a.email:
            lines.append(tex(a.email))
        blocks.append(r"\IEEEauthorblockN{" + tex(a.name) + r"}" + "\n" + r"\IEEEauthorblockA{" + r" \\ ".join(lines) + "}")
    front = r"\title{" + tex(p.title) + "}\n" + r"\author{" + "\n\\and\n".join(blocks) + "}\n\\maketitle"
    return _doc(r"\documentclass[conference]{IEEEtran}", front)


def ieee_journal(p: Paper) -> str:
    """IEEE Transactions: names in a line, affiliations as 'X and Y are with ...' footnotes."""
    groups: dict = {}
    for a in p.authors:
        groups.setdefault(tuple(f.id for f in a.affiliations), []).append(a)
    notes = []
    for _, people in groups.items():
        names = people[0].name if len(people) == 1 else ", ".join(x.name for x in people[:-1]) + " and " + people[-1].name
        verb = "is" if len(people) == 1 else "are"
        where = "; and also with ".join(_aff_lines(f) for f in people[0].affiliations)
        mails = ", ".join(x.email for x in people if x.email)
        notes.append(tex(f"{names} {verb} with ") + where + (r" (e-mail: " + tex(mails) + ")." if mails else "."))
    names = ", ".join(tex(a.name) for a in p.authors[:-1])
    names = (names + ", and " if len(p.authors) > 2 else names + " and " if names else "") + tex(p.authors[-1].name)
    front = (r"\title{" + tex(p.title) + "}\n" + r"\author{" + names + r"\thanks{" + " ".join(notes) + "}}\n\\maketitle")
    return _doc(r"\documentclass[journal]{IEEEtran}", front)


# ------------------------------------------------------------ ACM
def _acm(option: str):
    def render(p: Paper) -> str:
        parts = []
        for a in p.authors:
            s = r"\author{" + tex(a.name) + "}\n"
            if a.email:
                s += r"\email{" + tex(a.email) + "}\n"
            for f in a.affiliations:
                s += (r"\affiliation{\department{" + tex(f.department) + r"}\institution{" + tex(f.institution) +
                      r"}\city{" + tex(f.city) + r"}\country{" + tex(f.country) + "}}\n")
            parts.append(s)
        pre = (r"\documentclass[" + option + r"]{acmart}" + "\n" + r"\settopmatter{printacmref=false}" + "\n" +
               r"\setcopyright{none}\renewcommand\footnotetextcopyrightpermission[1]{}")
        front = (r"\title{" + tex(p.title) + "}\n" + "".join(parts) +
                 r"\begin{abstract}" + ABSTRACT + r"\end{abstract}" + "\n" +
                 r"\keywords{" + ", ".join(KEYWORDS) + "}\n\\maketitle")
        return f"{pre}\n\\begin{{document}}\n{front}\n{BODY}\n{REFS}\n\\end{{document}}\n"
    return render


# ------------------------------------------------------------ Springer LNCS
def lncs(p: Paper) -> str:
    authors = r" \and ".join(tex(a.name) + r"\inst{" + _marks(p, a) + "}" for a in p.authors)
    insts = []
    for f in p.affiliations:
        mails = [a.email for a in p.authors if a.email and a.affiliations[0] is f]
        line = _aff_lines(f) + ((r" \\ \email{" + tex(", ".join(mails)) + "}") if mails else "")
        insts.append(line)
    front = (r"\title{" + tex(p.title) + "}\n" + r"\author{" + authors + "}\n" + r"\institute{" + " \\and\n".join(insts) +
             "}\n\\maketitle")
    return _doc(r"\documentclass[runningheads]{llncs}", front)


# ------------------------------------------------------------ Elsevier
def _elsarticle(options: str):
    def render(p: Paper) -> str:
        lines = []
        for a in p.authors:
            mark = r"\corref{cor1}" if a.corresponding else ""
            lines.append(r"\author[" + _marks(p, a) + "]{" + tex(a.name) + mark + "}")
            if a.email:
                lines.append(r"\ead{" + tex(a.email) + "}")
        for f in p.affiliations:
            lines.append(r"\affiliation[" + f.id + r"]{organization={" + tex(f.department) + ", " + tex(f.institution) +
                         r"}, city={" + tex(f.city) + r"}, country={" + tex(f.country) + "}}")
        lines.append(r"\cortext[cor1]{Corresponding author}")
        front = (r"\begin{frontmatter}" + "\n" + r"\title{" + tex(p.title) + "}\n" + "\n".join(lines) + "\n" +
                 r"\begin{abstract}" + ABSTRACT + r"\end{abstract}" + "\n" +
                 r"\begin{keyword}" + r" \sep ".join(KEYWORDS) + r"\end{keyword}" + "\n" + r"\end{frontmatter}")
        return f"\\documentclass[{options}]{{elsarticle}}\n\\begin{{document}}\n{front}\n{BODY}\n{REFS}\n\\end{{document}}\n"
    return render


# ------------------------------------------------------------ physics and astronomy
def revtex(p: Paper) -> str:
    lines = []
    for a in p.authors:
        lines.append(r"\author{" + tex(a.name) + "}")
        if a.email:
            lines.append(r"\email{" + tex(a.email) + "}")
        for f in a.affiliations:
            lines.append(r"\affiliation{" + _aff_lines(f) + "}")
    front = (r"\title{" + tex(p.title) + "}\n" + "\n".join(lines) + "\n" +
             r"\begin{abstract}" + ABSTRACT + r"\end{abstract}" + "\n\\maketitle")
    return f"\\documentclass[aps,prl,twocolumn]{{revtex4-2}}\n\\begin{{document}}\n{front}\n{BODY}\n{REFS}\n\\end{{document}}\n"


def mnras(p: Paper) -> str:
    names = []
    for a in p.authors:
        mark = "$^{" + _marks(p, a) + "}$"
        names.append(tex(a.name) + mark + (r"\thanks{E-mail: " + tex(a.email) + "}" if a.corresponding else ""))
    places = r"\\".join("$^{" + f.id + "}$" + _aff_lines(f) for f in p.affiliations)
    short = tex(p.authors[0].family) + (" et al." if len(p.authors) > 1 else "")
    front = (r"\title{" + tex(p.title) + "}\n" + r"\author[" + short + "]{" + ", ".join(names) + r"\\" + places + "}\n" +
             r"\date{}" + "\n\\maketitle")
    return _doc(r"\documentclass[fleqn]{mnras}", front, abstract_after_front=True)


# ------------------------------------------------------------ chemistry
def achemso(p: Paper) -> str:
    lines = []
    for a in p.authors:
        lines.append(r"\author{" + tex(a.name) + "}")
        for f in a.affiliations:
            lines.append(r"\affiliation{" + _aff_lines(f) + "}")
        if a.corresponding:
            lines.append(r"\email{" + tex(a.email) + "}")
    pre = r"\documentclass[journal=jacsat,manuscript=article]{achemso}" + "\n" + "\n".join(lines) + "\n" + r"\title{" + tex(p.title) + "}"
    return f"{pre}\n\\begin{{document}}\n\\begin{{abstract}}{ABSTRACT}\\end{{abstract}}\n{BODY}\n{REFS}\n\\end{{document}}\n"


# ------------------------------------------------------------ mathematics (addresses at the END of the paper)
def amsart(p: Paper) -> str:
    lines = []
    for a in p.authors:
        lines.append(r"\author{" + tex(a.name) + "}")
        for f in a.affiliations:
            lines.append(r"\address{" + _aff_lines(f) + "}")
        if a.email:
            lines.append(r"\email{" + tex(a.email) + "}")
    front = r"\title{" + tex(p.title) + "}\n" + "\n".join(lines) + "\n" + r"\begin{abstract}" + ABSTRACT + r"\end{abstract}" + "\n\\maketitle"
    return f"\\documentclass{{amsart}}\n\\begin{{document}}\n{front}\n{BODY}\n{REFS}\n\\end{{document}}\n"


# ------------------------------------------------------------ machine learning
def jmlr(p: Paper) -> str:
    """The official jmlr class (JMLR and PMLR proceedings)."""
    parts = []
    for a in p.authors:
        s = (r"\Name{" + tex(a.name) + "}" + (r" \Email{" + tex(a.email) + "}" if a.email else "") +
             r" \\ \addr " + r" \\ ".join(_aff_lines(f) for f in a.affiliations))
        parts.append(s)
    front = r"\title{" + tex(p.title) + "}\n" + r"\author{" + "\n\\AND\n".join(parts) + "}\n\\maketitle"
    return _doc(r"\documentclass[pmlr]{jmlr}" + "\n" + r"\setcitestyle{numbers}", front)


# ------------------------------------------------------------ plain arXiv preprints
def article_authblk(p: Paper) -> str:
    lines = [r"\author[" + _marks(p, a) + "]{" + tex(a.name) + ("*" if a.corresponding else "") + "}" for a in p.authors]
    lines += [r"\affil[" + f.id + "]{" + _aff_lines(f) + "}" for f in p.affiliations]
    corr = next(a for a in p.authors if a.corresponding)
    pre = (r"\documentclass[11pt]{article}" + "\n" + r"\usepackage{authblk}" + "\n" + r"\title{" + tex(p.title) + "}\n" +
           "\n".join(lines) + "\n" + r"\date{}")
    front = r"\maketitle" + "\n" + r"\noindent *Corresponding author: " + tex(corr.email) + r"\par"
    return _doc(pre, front)


def article_blocks(p: Paper) -> str:
    """The plainest preprint: one block per author with name, place and email."""
    blocks = [tex(a.name) + r" \\ " + r" \\ ".join(tex(f.institution) + ", " + tex(f.country) for f in a.affiliations) +
              (r" \\ \texttt{" + tex(a.email) + "}" if a.email else "") for a in p.authors]
    pre = r"\documentclass[11pt]{article}" + "\n" + r"\title{" + tex(p.title) + "}\n" + r"\author{" + " \\and ".join(blocks) + "}\n" + r"\date{}"
    return _doc(pre, r"\maketitle")


# Truth for the affiliation of article_blocks is "institution, country" (no department or city).
SHORT_AFFILIATIONS = {"article-blocks"}

STYLES = {
    "ieee-conference": (ieee_conference, {"corresponding": False, "emails": "all"}),
    "ieee-journal": (ieee_journal, {"corresponding": False, "emails": "all"}),
    "acm-sigconf": (_acm("sigconf"), {"corresponding": False, "emails": "all"}),
    "acm-acmsmall": (_acm("acmsmall"), {"corresponding": False, "emails": "all"}),
    "springer-lncs": (lncs, {"corresponding": False, "emails": "first-affiliation"}),
    "elsevier-preprint": (_elsarticle("preprint,12pt"), {"corresponding": True, "emails": "all"}),
    "elsevier-5p": (_elsarticle("5p,times,twocolumn"), {"corresponding": True, "emails": "all"}),
    "aps-revtex": (revtex, {"corresponding": False, "emails": "all"}),
    "mnras": (mnras, {"corresponding": True, "emails": "corresponding"}),
    "acs-achemso": (achemso, {"corresponding": True, "emails": "corresponding"}),
    "ams-amsart": (amsart, {"corresponding": False, "emails": "all"}),
    "jmlr": (jmlr, {"corresponding": False, "emails": "all"}),
    "arxiv-authblk": (article_authblk, {"corresponding": True, "emails": "corresponding"}),
    "arxiv-blocks": (article_blocks, {"corresponding": False, "emails": "all"}),
}
