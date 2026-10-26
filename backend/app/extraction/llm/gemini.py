"""Gemini API over REST, with JSON-schema output."""
from __future__ import annotations

import json

import httpx

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _to_gemini(schema: dict) -> dict:
    out = {}
    for k, v in schema.items():
        if k == "type":
            out[k] = v.upper()
        elif k == "properties":
            out[k] = {name: _to_gemini(s) for name, s in v.items()}
        elif k == "items":
            out[k] = _to_gemini(v)
        elif k == "required":
            out[k] = v
    return out


def call(instructions: str, prompt: str, schema: dict, api_key: str, model: str, timeout: float) -> dict:
    body = {
        "systemInstruction": {"parts": [{"text": instructions}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": _to_gemini(schema),
        },
    }
    r = httpx.post(URL.format(model=model), headers={"x-goog-api-key": api_key}, json=body, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)
