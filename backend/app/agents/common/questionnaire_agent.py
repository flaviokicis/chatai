from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from app.agents.base import BaseAgent, BaseAgentDeps
from app.core.messages import AgentResult, InboundMessage, OutboundMessage

from .state_types import AnswersBlob

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
        blob = AnswersBlob.from_unknown(self.deps.store.load(self.user_id, self.agent_type))
        return blob.answers, blob.pending_field

    def _save_answers(self, answers: dict[str, Any], pending_field: str | None) -> None:
        self.deps.store.save(
            self.user_id,
            self.agent_type,
            AnswersBlob(answers=answers, pending_field=pending_field).model_dump(),
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

        # Decide next question directly from the question graph
        state_like = SimpleNamespace(answers=answers, pending_field=None)
        next_q = self.qg.next_missing(state_like)
        next_prompt = next_q.prompt if next_q else None
        if next_prompt is None:
            self._save_answers(answers, pending_field)
            return self._escalate("checklist_complete", {"answers": answers})

        # Update pending_field to match the question key obtained by prompt lookup
        q = self.qg.get_by_prompt(next_prompt)
        pending_field = q.key if q else None
        self._save_answers(answers, pending_field)
        return AgentResult(outbound=OutboundMessage(text=next_prompt), handoff=None, state_diff={})
