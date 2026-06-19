"""Pure review-gate function: decide if a lead needs human review.

Deterministic and side-effect-free. Enum-aware for intent.
"""

from __future__ import annotations

from app.core.enums import Intent


def requires_review(score: int, intent: str | Intent | None) -> bool:
    if score < 50:
        return True
    intent_value = intent.value if isinstance(intent, Intent) else (intent or "")
    if str(intent_value).lower() == "inquiry":
        return True
    return False
