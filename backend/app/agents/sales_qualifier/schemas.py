from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SalesQualifierState(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    pending_field: str | None = None

    def to_dict(self) -> dict:  # type: ignore[override]
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> SalesQualifierState:  # type: ignore[override]
        return cls(**data)


class UpdateAnswers(BaseModel):
    updates: dict[str, Any] = Field(
        default_factory=dict, description="Key-value updates for answers map"
    )
