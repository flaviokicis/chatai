from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .messages import AgentResult, InboundMessage


class AgentState(Protocol):
    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentState: ...

    def is_complete(self) -> bool: ...


class Agent(ABC):
    agent_type: str

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    def get_agent_type(self) -> str:
        """Return the concrete agent type for routing/analytics consistency."""
        return self.agent_type

    @abstractmethod
    def handle(self, message: InboundMessage) -> AgentResult:
        raise NotImplementedError
