"""Validated contract for LLM qualification output (anti-corruption layer).

Raw LLM output is untrusted: keys may be missing, types wrong, enums
free-text, score out of range. This contract coerces and bounds everything
before it touches the domain, so the pipeline can rely on typed, in-range
values instead of accessing `ai_result["score"]` blindly (audit finding #10).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.enums import Intent, Urgency


class QualificationContract(BaseModel):
    """Normalized, validated qualification result."""

    intent: Intent = Intent.UNKNOWN
    budget: str | None = None
    budget_amount: float | None = None
    timeline: str | None = None
    location: str | None = None
    urgency: Urgency = Urgency.LOW
    score: int = 0
    ai_summary: str | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("intent", mode="before")
    @classmethod
    def _coerce_intent(cls, v):
        try:
            return Intent(str(v).strip().lower())
        except (ValueError, AttributeError):
            return Intent.UNKNOWN

    @field_validator("urgency", mode="before")
    @classmethod
    def _coerce_urgency(cls, v):
        try:
            return Urgency(str(v).strip().lower())
        except (ValueError, AttributeError):
            return Urgency.LOW

    @field_validator("score", mode="before")
    @classmethod
    def _coerce_score(cls, v):
        try:
            return max(0, min(100, int(float(v))))
        except (TypeError, ValueError):
            return 0

    @field_validator("budget", "timeline", "location", "ai_summary", mode="before")
    @classmethod
    def _stringify(cls, v):
        if v is None:
            return None
        return str(v).strip() or None

    @classmethod
    def from_raw(cls, raw: dict) -> "QualificationContract":
        """Build from an arbitrary LLM dict, never raising on bad input."""
        if not isinstance(raw, dict):
            raw = {}
        return cls.model_validate(raw)
