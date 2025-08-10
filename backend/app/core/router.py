from __future__ import annotations

from typing import TYPE_CHECKING

from .messages import InboundMessage, OutboundMessage

if TYPE_CHECKING:
    from collections.abc import Callable

    from .agent_base import Agent
    from .state import ConversationStore


class MessageRouter:
    def __init__(
        self,
        store: ConversationStore,
        registry: dict[str, Callable[[str], Agent]],
        default_agent_type: str,
    ) -> None:
        self.store = store
        self.registry = registry
        self.default_agent_type = default_agent_type

    def _resolve_agent_type(self, _message: InboundMessage) -> str:
        return self.default_agent_type

    def route(self, message: InboundMessage) -> OutboundMessage:
        agent_type = self._resolve_agent_type(message)
        ctor = self.registry.get(agent_type)
        if not ctor:
            return OutboundMessage(text="Sorry, no agent available right now.")
        agent = ctor(message.user_id)
        result = agent.handle(message)
        # Persisting of state is left to the agent for now.
        if result.handoff:
            # The adapter may also take action based on handoff if needed.
            pass
        return result.outbound or OutboundMessage(text="")
