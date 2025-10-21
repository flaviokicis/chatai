from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeGuard

DebounceResult = Literal["exit", "process_aggregated", "process_single"]


@dataclass(frozen=True, slots=True)
class BufferedMessage:
    content: str
    timestamp: float
    sequence: int
    id: str


def is_buffered_message(data: Any) -> TypeGuard[BufferedMessage]:
    """Runtime type guard for BufferedMessage."""
    return isinstance(data, BufferedMessage)


def is_debounce_result(value: str) -> TypeGuard[DebounceResult]:
    """Runtime type guard for DebounceResult."""
    return value in ("exit", "process_aggregated", "process_single")

