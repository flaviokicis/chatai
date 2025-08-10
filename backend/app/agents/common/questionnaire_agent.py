from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.agents.base import BaseAgent, BaseAgentDeps
from app.core.messages import AgentResult, InboundMessage, OutboundMessage

if TYPE_CHECKING:
    from .question_graph import QuestionGraph
from .questionnaire_extractor import QuestionnaireExtractor


class QuestionnaireAgent(BaseAgent):
    agent_type = "questionnaire"

    def __init__(self, user_id: str, deps: BaseAgentDeps, question_graph: QuestionGraph) -> None:
        super().__init__(user_id, deps)
        self.qg = question_graph
        self.extractor = QuestionnaireExtractor(deps.llm)

    def _load_answers(self) -> tuple[dict[str, Any], str | None]:
        # Store answers/pending in a single blob via store for generic agents
        state = self.deps.store.load(self.user_id, self.agent_type)
        if isinstance(state, dict):
            answers = state.get("answers", {}) if isinstance(state.get("answers"), dict) else {}
            pending = (
                state.get("pending_field") if isinstance(state.get("pending_field"), str) else None
            )
            return answers, pending
        return {}, None

    def _save_answers(self, answers: dict[str, Any], pending_field: str | None) -> None:
        self.deps.store.save(
            self.user_id, self.agent_type, {"answers": answers, "pending_field": pending_field}
        )

    def handle(self, message: InboundMessage) -> AgentResult:
        answers, pending_field = self._load_answers()
        args = self.extractor.extract(answers, pending_field, self.qg)
        if args.get("__tool_name__") == "EscalateToHuman":
            reason = str(args.get("reason", "llm_escalation"))
            summary = {"answers": answers}
            self._save_answers(answers, pending_field)
            return self._escalate(reason, summary)

        # Apply updates conservatively
        updates = (args.get("updates") or {}) if isinstance(args, dict) else {}
        for k, v in updates.items():
            if k not in answers:
                answers[k] = v
        if pending_field and pending_field in answers and answers[pending_field] not in (None, ""):
            pending_field = None

        # Decide next question
        next_q = self.qg.next_missing(type("S", (), {"answers": answers})())
        if next_q is None:
            self._save_answers(answers, pending_field)
            return self._escalate("checklist_complete", {"answers": answers})

        pending_field = next_q.key
        self._save_answers(answers, pending_field)
        return AgentResult(
            outbound=OutboundMessage(text=next_q.prompt), handoff=None, state_diff={}
        )
