"""Groq API (OpenAI-compatible) in JSON mode."""
from __future__ import annotations

import json

import httpx

URL = "https://api.groq.com/openai/v1/chat/completions"


def call(instructions: str, prompt: str, schema: dict, api_key: str, model: str, timeout: float) -> dict:
    system = instructions + "\nReply with JSON only, matching this JSON schema:\n" + json.dumps(schema)
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    }
    r = httpx.post(URL, headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=timeout)
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])
