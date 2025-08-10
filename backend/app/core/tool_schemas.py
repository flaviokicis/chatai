from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EscalateToHuman(BaseModel):
    reason: str = Field(..., description="Short machine-readable reason for escalation")
    summary: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured summary/context for the human",
    )


class UpdateAnswers(BaseModel):
    updates: dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value updates for answers map",
    )
