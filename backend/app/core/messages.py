from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InboundMessage:
    user_id: str
    text: str
    channel: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OutboundMessage:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentResult:
    outbound: OutboundMessage | None
    handoff: dict[str, Any] | None
    state_diff: dict[str, Any] = field(default_factory=dict)
