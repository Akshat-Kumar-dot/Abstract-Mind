"""Made-up but realistic author lists for template test papers.

Covers what trips readers up: names from many regions, accents, hyphens,
particles ("van der"), one or several affiliations per author, affiliations
shared by several authors, authors without an email, and one corresponding
author. Seeded, so the same paper number always gives the same people.
"""
from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field

GIVEN = {
    "india": ["Aarav", "Priya", "Rohan", "Ananya", "Vikram", "Meera", "Arjun", "Kavya", "Siddharth", "Lakshmi", "Rahul", "Shreya"],
    "china": ["Wei", "Xiaoming", "Li", "Jing", "Hao", "Yan", "Zhiwei", "Mei", "Jun", "Xin"],
    "korea": ["Min-jun", "Seo-yeon", "Ji-hoon", "Ha-eun"],
    "arab": ["Omar", "Fatima", "Youssef", "Layla", "Karim"],
    "europe": ["Anna", "Lukas", "Sophie", "Matteo", "Élodie", "João", "Søren", "Zoë", "Jan", "María José"],
    "us": ["Emily", "Michael", "Sarah", "David", "Olivia", "James"],
}
FAMILY = {
    "india": ["Sharma", "Iyer", "Reddy", "Banerjee", "Nair", "Patel", "Gupta", "Krishnamurthy", "Chatterjee", "Singh"],
    "china": ["Zhang", "Wang", "Li", "Chen", "Liu", "Huang", "Zhao", "Xu"],
    "korea": ["Kim", "Park", "Lee", "Choi"],
    "arab": ["Haddad", "Al-Farsi", "Mansour", "El-Sayed"],
    "europe": ["Müller", "van der Berg", "Rossi", "Dubois", "Kowalski", "Nielsen", "García-López", "Schäfer", "de Souza", "O'Brien"],
    "us": ["Johnson", "Miller", "Davis", "Anderson", "Thompson", "Walker"],
}
PLACES = [
    ("Department of Computer Science and Engineering", "Indian Institute of Technology Delhi", "New Delhi", "India", "iitd.ac.in"),
    ("School of Electrical Engineering", "Vellore Institute of Technology", "Vellore", "India", "vit.ac.in"),
    ("Department of Physics", "University of Calcutta", "Kolkata", "India", "caluniv.ac.in"),
    ("Department of Information Technology", "Manipal University Jaipur", "Jaipur", "India", "jaipur.manipal.edu"),
    ("Institute of Automation", "Chinese Academy of Sciences", "Beijing", "China", "ia.ac.cn"),
    ("School of Software", "Tsinghua University", "Beijing", "China", "tsinghua.edu.cn"),
    ("Department of Electrical Engineering", "KAIST", "Daejeon", "South Korea", "kaist.ac.kr"),
    ("Faculty of Engineering", "Cairo University", "Giza", "Egypt", "eng.cu.edu.eg"),
    ("Department of Informatics", "Technical University of Munich", "Munich", "Germany", "tum.de"),
    ("Faculty of Science", "University of Amsterdam", "Amsterdam", "Netherlands", "uva.nl"),
    ("Dipartimento di Informatica", "Università di Pisa", "Pisa", "Italy", "unipi.it"),
    ("Laboratoire d'Informatique", "Sorbonne Université", "Paris", "France", "sorbonne-universite.fr"),
    ("Department of Computer Science", "Columbia University", "New York", "USA", "cs.columbia.edu"),
    ("Department of Statistics", "University of Oxford", "Oxford", "UK", "stats.ox.ac.uk"),
    ("Nokia Bell Labs", "Nokia", "Murray Hill", "USA", "nokia-bell-labs.com"),
    ("Microsoft Research India", "Microsoft", "Bengaluru", "India", "microsoft.com"),
]
TITLES = [
    "Graph Neural Networks for Monsoon Rainfall Forecasting over the Western Ghats",
    "A Lightweight Transformer for Real-Time Traffic Sign Recognition on Edge Devices",
    "Federated Learning with Differential Privacy for Hospital Readmission Prediction",
    "Robust Speech Recognition for Code-Mixed Hindi-English Conversations",
    "Energy-Efficient Scheduling of Deep Learning Workloads in Heterogeneous Clusters",
    "Detecting Misinformation in Regional Language News Using Contrastive Learning",
    "Quantum-Inspired Optimisation for Vehicle Routing with Time Windows",
    "Self-Supervised Learning of Crop Health Indicators from Satellite Imagery",
]


@dataclass
class Affiliation:
    id: str
    department: str
    institution: str
    city: str
    country: str
    domain: str

    @property
    def text(self) -> str:
        return f"{self.department}, {self.institution}, {self.city}, {self.country}"


@dataclass
class Author:
    given: str
    family: str
    affiliations: list[Affiliation]
    email: str | None
    corresponding: bool = False

    @property
    def name(self) -> str:
        return f"{self.given} {self.family}"


@dataclass
class Paper:
    id: str
    title: str
    authors: list[Author]
    affiliations: list[Affiliation] = field(default_factory=list)

    def truth(self, style: str) -> dict:
        return {"style": style, "id": self.id, "title": self.title, "authors": [
            {"given": a.given, "family": a.family, "name": a.name, "emails": [a.email] if a.email else [],
             "affiliations": [f.text for f in a.affiliations], "corresponding": a.corresponding} for a in self.authors]}


def _ascii(s: str) -> str:
    """Letters as they'd appear in an email address: Søren -> soren, Müller -> muller."""
    s = s.translate(str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "ß": "ss", "ł": "l", "đ": "d"}))
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c) and (c.isalnum() or c in ".-")).lower()


def _email(given: str, family: str, domain: str, rng: random.Random) -> str:
    g, f = _ascii(given.split()[0]).replace("-", ""), _ascii(family.split()[-1]).replace("-", "")
    local = rng.choice([f"{g}.{f}", f"{g[0]}{f}", f"{g}{f[0]}", f"{f}.{g[0]}", f"{g}_{f}", f"{g}"])
    return f"{local}@{domain}"


def make_paper(n: int, *, min_authors: int = 1, max_authors: int = 8) -> Paper:
    rng = random.Random(n)
    places = rng.sample(PLACES, rng.choice([1, 1, 2, 2, 3, 4]))
    affs = [Affiliation(str(i + 1), *p) for i, p in enumerate(places)]
    count = rng.randint(max(min_authors, len(affs)), max(max_authors, len(affs)))
    authors, used = [], set()
    for i in range(count):
        region = rng.choice(list(GIVEN))
        given, family = rng.choice(GIVEN[region]), rng.choice(FAMILY[region])
        while f"{given} {family}" in used:
            given = rng.choice(GIVEN[region])
            family = rng.choice(FAMILY[rng.choice(list(FAMILY))])
        used.add(f"{given} {family}")
        mine = [affs[i % len(affs)]] if i < len(affs) else [rng.choice(affs)]
        if len(affs) > 1 and rng.random() < 0.2:                       # a second affiliation
            mine.append(rng.choice([a for a in affs if a not in mine]))
        email = _email(given, family, mine[0].domain, rng) if rng.random() < 0.75 else None
        authors.append(Author(given, family, mine, email))
    corresponding = rng.choice([a for a in authors if a.email] or authors)
    if not corresponding.email:
        corresponding.email = _email(corresponding.given, corresponding.family, corresponding.affiliations[0].domain, rng)
    corresponding.corresponding = True
    used_affs = []
    for x in authors:                                                   # number them in order of first use
        used_affs += [a for a in x.affiliations if a not in used_affs]
    for i, a in enumerate(used_affs):
        a.id = str(i + 1)
    return Paper(id=f"synth-{n:04d}", title=rng.choice(TITLES), authors=authors, affiliations=used_affs)
