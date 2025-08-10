from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from app.agents.base import BaseAgent, BaseAgentDeps
from app.core.messages import AgentResult, InboundMessage, OutboundMessage
from app.settings import is_debug_enabled

from .answers_updater import (
    apply_updates_conservatively,
    extract_normalized_updates,
)
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

    # --- Lifecycle and hooks (overridable by subclasses) ---
    def _load_blob(self) -> AnswersBlob:
        return AnswersBlob.from_unknown(self.deps.store.load(self.user_id, self.agent_type))

    def _save_blob(self, blob: AnswersBlob) -> None:
        self.deps.store.save(self.user_id, self.agent_type, blob.model_dump())

    def _load_answers(self) -> tuple[dict[str, Any], str | None]:
        blob = self._load_blob()
        return blob.answers, blob.pending_field

    def _save_answers(self, answers: dict[str, Any], pending_field: str | None) -> None:
        self.deps.store.save(
            self.user_id,
            self.agent_type,
            AnswersBlob(answers=answers, pending_field=pending_field).model_dump(),
        )

    def _allowed_keys(self, blob: AnswersBlob) -> list[str]:
        # Default: keys from the effective graph for current context
        return self._effective_graph(blob).keys()

    def _effective_graph(self, blob: AnswersBlob) -> QuestionGraph:
        # Default: only global graph
        return self.qg

    def _update_context_from_message(
        self, blob: AnswersBlob, message: InboundMessage
    ) -> AnswersBlob:
        return blob

    def handle(self, message: InboundMessage) -> AgentResult:
        blob = self._load_blob()
        answers, pending_field = blob.answers, blob.pending_field

        # Allow subclass to update selection/context first (e.g., path selection)
        blob = self._update_context_from_message(blob, message)
        # Use effective graph (may include a selected subgraph) for extraction
        effective_for_extraction = self._effective_graph(blob)
        args = self.extractor.extract(
            message.text or "",
            answers,
            pending_field,
            effective_for_extraction,
        )
        if is_debug_enabled():
            try:
                logging.getLogger("uvicorn.error").info(
                    "[dev_debug] extractor tool=%s updates_keys=%s pending_before=%s",
                    (args.get("__tool_name__") if isinstance(args, dict) else "<none>"),
                    list((args.get("updates") or {}).keys())
                    if isinstance(args, dict) and isinstance(args.get("updates"), dict)
                    else [],
                    pending_field,
                )
            except Exception:
                logging.getLogger("uvicorn.error").debug(
                    "[dev_debug] logging failed while reporting extractor info", exc_info=True
                )
        if args.get("__tool_name__") == "EscalateToHuman":
            reason = str(args.get("reason", "llm_escalation"))
            summary = {"answers": answers}
            self._save_blob(blob)
            return self._escalate(reason, summary)

        # Apply updates via centralized updater
        updates = extract_normalized_updates(args)
        # If UnknownAnswer was returned without a field, map it to the pending field
        if (
            isinstance(args, dict)
            and args.get("__tool_name__") == "UnknownAnswer"
            and pending_field
            and (not updates or len(updates) == 0)
        ):
            updates = {pending_field: "unknown"}

        answers, pending_field, _ = apply_updates_conservatively(
            answers=answers,
            updates=updates,
            pending_field=pending_field,
            allowed_keys=self._allowed_keys(blob),
        )
        if is_debug_enabled():
            try:
                logging.getLogger("uvicorn.error").info(
                    "[dev_debug] applied updates=%s pending_after=%s",
                    list(updates.keys()) if isinstance(updates, dict) else [],
                    pending_field,
                )
            except Exception:
                logging.getLogger("uvicorn.error").debug(
                    "[dev_debug] logging failed while reporting applied updates", exc_info=True
                )
        blob.answers = answers
        blob.pending_field = pending_field

        # Decide next question using the effective graph for the current context
        effective = self._effective_graph(blob)
        state_like = SimpleNamespace(answers=answers, pending_field=None)
        next_q = effective.next_missing(state_like)
        next_prompt = next_q.prompt if next_q else None
        if next_prompt is None:
            self._save_blob(blob)
            return self._escalate("checklist_complete", {"answers": answers})

        # Update pending_field to match the question key obtained by prompt lookup
        q = effective.get_by_prompt(next_prompt)
        blob.pending_field = q.key if q else None
        self._save_blob(blob)

        # Naturalize prompt centrally
        from app.core.naturalize import naturalize_prompt

        varied_text = naturalize_prompt(self.deps.llm, next_prompt)
        return AgentResult(outbound=OutboundMessage(text=varied_text), handoff=None, state_diff={})
