"""Flow processing response models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FlowProcessingResult(Enum):
    """Result types for flow processing."""

    CONTINUE = "continue"
    TERMINAL = "terminal"
    ESCALATE = "escalate"
    ERROR = "error"


@dataclass
class FlowResponse:
    """Response from flow processing."""

    result: FlowProcessingResult
    message: str
    context: Any | None = None
    metadata: dict[str, Any] | None = None

    @property
    def is_success(self) -> bool:
        """Check if the processing was successful."""
        return self.result != FlowProcessingResult.ERROR
