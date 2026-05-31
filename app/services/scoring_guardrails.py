"""Score normalization guardrails.

Null-safe: the LLM can return budget as a number, null, or arbitrary text, and
urgency may be missing. The previous version called ``budget.lower()``
unconditionally and crashed (AttributeError) on anything but a string, killing
the Celery task and burning all retries (audit critical #7).
"""

from __future__ import annotations

from app.core.enums import Urgency


def normalize_score(
    score: int | None,
    urgency: str | Urgency | None,
    budget: str | float | int | None,
) -> int:
    normalized = int(score) if score is not None else 0

    budget_text = str(budget).lower() if budget is not None else ""
    if "cr" in budget_text or "crore" in budget_text:
        normalized = max(normalized, 85)

    urgency_value = urgency.value if isinstance(urgency, Urgency) else (urgency or "")
    if str(urgency_value).lower() == "high":
        normalized = max(normalized, 90)

    return max(0, min(100, normalized))
