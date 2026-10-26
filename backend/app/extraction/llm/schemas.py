"""The fixed JSON shape the LLM must fill for a manuscript header."""

PAPER_HEADER = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "authors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "orcid": {"type": "string"},
                    "affiliations": {"type": "array", "items": {"type": "string"}},
                    "corresponding": {"type": "boolean"},
                },
                "required": ["name", "affiliations"],
            },
        },
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "authors", "keywords"],
}

INSTRUCTIONS = """You read the header of an unpublished research manuscript and return JSON.
Rules:
- Copy every value exactly as written in the text. Never invent, translate or complete anything.
- Authors are only the people who wrote THIS paper, in the order printed. Ignore cited authors, editors and people thanked.
- Superscript markers appear as ^{...}; use them to link authors to affiliations, then leave them out of the values.
- An affiliation is the full text for one institution (department, institution, city, country).
- Use an empty string or empty list when something is not in the text.
"""
