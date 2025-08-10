from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class AnswersState(Protocol):
    answers: dict[str, Any]
    pending_field: str | None


class AnswersBlob(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    pending_field: str | None = None
    # Path-aware extensions (optional; ignored if not using paths)
    active_path: str | None = None
    path_locked: bool = False

    @classmethod
    def from_unknown(cls, state: object) -> AnswersBlob:
        data: dict[str, Any] = state if isinstance(state, dict) else {}
        # Pydantic will coerce and fill defaults
        return cls(**data)
