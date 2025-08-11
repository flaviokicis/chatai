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


class FlowAgent(BaseAgent):
    """Generic agent that delegates state progression to flow_core.Engine.

    Concrete agents can subclass this, providing a Flow (or params convertible to one)
    and a Responder for value extraction.
    """

    agent_type = "flow"

    def __init__(self, user_id: str, deps: BaseAgentDeps, *, compiled_flow, responder) -> None:  # type: ignore[no-untyped-def]
        super().__init__(user_id, deps)
        self._compiled = compiled_flow
        self._responder = responder

    def handle(self, message):  # type: ignore[no-untyped-def]
        from app.core.messages import AgentResult, OutboundMessage
        from app.flow_core.engine import Engine

        engine = Engine(self._compiled)
        state = engine.start()
        stored = self.deps.store.load(self.user_id, self.agent_type) or {}
        answers = dict(stored.get("answers", {}))
        state.answers.update(answers)

        # step to get prompt
        out = engine.step(state)
        if out.kind == "terminal":
            return self._escalate("checklist_complete", {"answers": state.answers})

        # respond using configured responder
        from app.flow_core.responders import ResponderContext

        ctx = ResponderContext()
        r = self._responder.respond(out.message or "", state.pending_field, state.answers, message.text or "", ctx)

        for k, v in r.updates.items():
            state.answers[k] = v
        if state.pending_field and state.pending_field in r.updates:
            engine.step(state, {"answer": r.updates[state.pending_field], "tool_name": r.tool_name})

        self.deps.store.save(self.user_id, self.agent_type, {"answers": state.answers})
        reply = r.assistant_message or (out.message or "")
        return AgentResult(outbound=OutboundMessage(text=reply), handoff=None, state_diff={})
