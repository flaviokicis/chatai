from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .agent_base import AgentState


class ConversationStore(Protocol):
    def load(self, user_id: str, agent_type: str) -> AgentState | None: ...

    def save(self, user_id: str, agent_type: str, state: AgentState) -> None: ...

    def append_event(self, user_id: str, event: dict) -> None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._states: dict[tuple[str, str], AgentState] = {}
        self._events: dict[str, list[dict]] = {}

    def load(self, user_id: str, agent_type: str) -> AgentState | None:
        return self._states.get((user_id, agent_type))

    def save(self, user_id: str, agent_type: str, state: AgentState) -> None:
        self._states[(user_id, agent_type)] = state

    def append_event(self, user_id: str, event: dict) -> None:
        self._events.setdefault(user_id, []).append(event)
