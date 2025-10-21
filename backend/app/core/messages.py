from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .message_metadata import AgentResultMetadata, InboundMessageMetadata, OutboundMessageMetadata


@dataclass(slots=True)
class InboundMessage:
    user_id: str
    text: str
    channel: str
    metadata: InboundMessageMetadata = field(default_factory=InboundMessageMetadata)


@dataclass(slots=True)
class OutboundMessage:
    text: str
    metadata: OutboundMessageMetadata = field(default_factory=OutboundMessageMetadata)


@dataclass(slots=True)
class AgentResult:
    outbound: OutboundMessage | None
    handoff: dict[str, Any] | None
    state_diff: dict[str, Any] = field(default_factory=dict)
    metadata: AgentResultMetadata = field(default_factory=AgentResultMetadata)
