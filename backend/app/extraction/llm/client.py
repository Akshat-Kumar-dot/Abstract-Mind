"""One interface over Gemini and Groq; which one runs is set by LLM_PROVIDER.
Nothing is sent unless the person ticked "Let AI help" for that upload."""
from __future__ import annotations

import json
from typing import Optional

import httpx

from ...settings import get_settings
from . import gemini, groq


class LLMError(RuntimeError):
    pass


def provider() -> Optional[str]:
    return get_settings().llm_provider


def extract_json(instructions: str, prompt: str, schema: dict) -> dict:
    s = get_settings()
    p = s.llm_provider
    if p is None:
        raise LLMError("No LLM is configured")
    try:
        if p == "gemini":
            return gemini.call(instructions, prompt, schema, s.gemini_api_key, s.gemini_model, s.llm_timeout)
        return groq.call(instructions, prompt, schema, s.groq_api_key, s.groq_model, s.llm_timeout)
    except httpx.HTTPStatusError as e:
        raise LLMError(f"{p} returned HTTP {e.response.status_code}") from None
    except httpx.HTTPError as e:
        raise LLMError(f"Could not reach {p}: {type(e).__name__}") from None
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise LLMError(f"{p} returned an answer in an unexpected shape") from None
