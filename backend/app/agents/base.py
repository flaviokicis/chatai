from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.agent_base import Agent
from app.core.messages import AgentResult, OutboundMessage

if TYPE_CHECKING:  # pragma: no cover - import-time only for typing
    from app.core.llm import LLMClient
    from app.core.state import ConversationStore
    from app.core.tools import HumanHandoffTool


logger = logging.getLogger("uvicorn.error")


@dataclass(slots=True)
class BaseAgentDeps:
    store: ConversationStore
    llm: LLMClient
    handoff: HumanHandoffTool


class BaseAgent(Agent):
    def __init__(self, user_id: str, deps: BaseAgentDeps) -> None:
        super().__init__(user_id)
        self.deps = deps

    # Helper used by concrete agents
    def _escalate(self, reason: str, summary: dict[str, Any]) -> AgentResult:
        self.deps.handoff.escalate(self.user_id, reason, summary)
        return AgentResult(
            outbound=OutboundMessage(text="Transferring you to a human for further assistance."),
            handoff={"reason": reason, "summary": summary},
            state_diff={},
        )
