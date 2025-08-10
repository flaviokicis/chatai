from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class HumanHandoffTool(Protocol):
    def escalate(self, user_id: str, reason: str, summary: dict[str, Any]) -> None: ...


@dataclass(slots=True)
class HandoffArgs:
    reason: str
    summary: dict[str, Any]
