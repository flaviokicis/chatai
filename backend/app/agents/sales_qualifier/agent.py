from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.agents.base import BaseAgent, BaseAgentDeps
from app.agents.common.policy import QuestionnairePolicy
from app.core.messages import AgentResult, InboundMessage, OutboundMessage
from app.core.state import ConversationStore  # noqa: F401 (imported for type clarity)

from .extractor import SalesExtractor

if TYPE_CHECKING:  # import only for typing
    from app.agents.common.question_graph import QuestionGraph
from .schemas import SalesQualifierState, UpdateAnswers


class SalesQualifierAgent(BaseAgent):
    agent_type = "sales_qualifier"

    def __init__(self, user_id: str, deps: BaseAgentDeps, question_graph: QuestionGraph) -> None:
        super().__init__(user_id, deps)
        self.extractor = SalesExtractor(deps.llm)
        self.policy = QuestionnairePolicy(question_graph)

    def _load_state(self) -> SalesQualifierState:
        state = self.deps.store.load(self.user_id, self.agent_type)
        if isinstance(state, SalesQualifierState):
            return state
        return SalesQualifierState()

    def _save_state(self, state: SalesQualifierState) -> None:
        self.deps.store.save(self.user_id, self.agent_type, state)

    def _apply_update(
        self, state: SalesQualifierState, args: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        before = state.model_dump()
        update = UpdateAnswers(**args)
        for k, v in (update.updates or {}).items():
            if k not in state.answers:
                state.answers[k] = v
        # Clear pending if answered
        if (
            state.pending_field
            and state.pending_field in state.answers
            and state.answers[state.pending_field] not in (None, "")
        ):
            state.pending_field = None
        after = state.model_dump()
        diff: dict[str, dict[str, Any]] = {}
        for k in before:
            if before[k] != after[k]:
                diff[k] = {"from": before[k], "to": after[k]}
        return diff

    def handle(self, message: InboundMessage) -> AgentResult:
        state = self._load_state()
        args = self.extractor.classify_and_update(state, message.text, self.policy.qg)
        # If LLM requested escalation, short-circuit
        if args.get("__tool_name__") == "EscalateToHuman":
            reason = str(args.get("reason", "llm_escalation"))
            summary = state.model_dump()
            summary.update({"llm_summary": args.get("summary")})
            self._save_state(state)
            return self._escalate(reason, summary)
        diff = self._apply_update(state, args)

        # Completion when no further question is missing
        if self.policy.next_prompt(state) is None:
            summary = state.model_dump()
            self._save_state(state)
            return self._escalate("checklist_complete", summary)

        next_prompt = self.policy.next_prompt(state)
        if next_prompt:
            # update pending field to match the question key via public getter
            q = self.policy.qg.get_by_prompt(next_prompt)
            state.pending_field = q.key if q else None
            self._save_state(state)
            return AgentResult(
                outbound=OutboundMessage(text=next_prompt),
                handoff=None,
                state_diff=diff,
            )

        # Fallback: escalate if policy deems necessary
        if self.policy.should_escalate(state):
            summary = state.model_dump()
            self._save_state(state)
            return self._escalate("policy_escalation", summary)

        # No next prompt and not complete: safe default
        self._save_state(state)
        return AgentResult(
            outbound=OutboundMessage(text="Transferring you to a human."),
            handoff={"reason": "no_next_prompt"},
            state_diff=diff,
        )
