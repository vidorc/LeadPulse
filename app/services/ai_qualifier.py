"""LLM-backed lead qualification (anti-corruption layer around the provider).

The Groq client is constructed lazily from `settings`, not at import time, so:
  * no API key is hardcoded in source (it comes from the single trust root);
  * importing this module never requires network/credentials (testable);
  * the provider can be swapped behind `complete()` without touching callers.

Raw LLM output is parsed defensively here; the caller is responsible for
validating it against a strict Pydantic contract before it touches the domain.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from app.core.config import settings

_QUALIFICATION_PROMPT = """\
Extract lead information as strict JSON only. Return ONLY valid JSON, no prose.

Fields (all required):
  intent      : one of "purchase", "inquiry", "support", "spam", "unknown"
  budget      : the stated budget as a string, or "unknown"
  location    : the location as a string, or "unknown"
  urgency     : one of "high", "medium", "low"
  timeline    : expected purchase timeline as a string, or "unknown"
  score       : integer 0-100 estimating lead quality
  ai_summary  : one-sentence summary of the lead

Lead source: {source}
Message: {message}
"""


@lru_cache(maxsize=1)
def _get_client():
    """Lazily build the Groq client. Cached so we reuse one connection pool."""
    from groq import Groq  # imported lazily to avoid hard dep at import time

    if not settings.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not configured; cannot run lead qualification."
        )
    return Groq(api_key=settings.GROQ_API_KEY)


def _strip_code_fences(content: str) -> str:
    """Remove ```json ... ``` fences that llama3 commonly wraps JSON in."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return content.strip()


def _extract_json(content: str) -> dict[str, Any]:
    """Best-effort parse of an LLM response into a dict."""
    cleaned = _strip_code_fences(content)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    # Last resort: grab the first {...} block.
    brace = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if brace:
        try:
            parsed = json.loads(brace.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError("LLM did not return parseable JSON")


def qualify_lead(source: str | None, message: str | None) -> dict[str, Any]:
    """Call the LLM and return a parsed (but not yet validated) result dict.

    Raises on transient/provider errors so the caller can retry only those;
    returns a conservative fallback dict only for unparseable-but-successful
    responses (so a malformed completion doesn't wedge the pipeline).
    """
    prompt = _QUALIFICATION_PROMPT.format(
        source=source or "unknown",
        message=message or "",
    )

    response = _get_client().chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    content = response.choices[0].message.content or ""

    try:
        return _extract_json(content)
    except ValueError:
        return {
            "intent": "unknown",
            "budget": "unknown",
            "location": "unknown",
            "urgency": "low",
            "timeline": "unknown",
            "score": 10,
            "ai_summary": "Fallback: LLM response could not be parsed.",
        }
