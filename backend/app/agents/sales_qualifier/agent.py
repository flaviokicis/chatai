from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.agents.common.questionnaire_agent import QuestionnaireAgent

if TYPE_CHECKING:
    from app.agents.common.state_types import AnswersBlob
    from app.core.messages import InboundMessage

from .extractor import SalesExtractor

if TYPE_CHECKING:  # import only for typing
    from app.agents.base import BaseAgentDeps
    from app.agents.common.question_graph import QuestionGraph


class SalesQualifierAgent(QuestionnaireAgent):
    agent_type = "sales_qualifier"

    @dataclass(slots=True)
    class SalesPathConfig:
        graphs: dict[str, Any] | None = None
        predicates: dict[str, list] | None = None
        settings: dict[str, Any] | None = None

    def __init__(
        self,
        user_id: str,
        deps: BaseAgentDeps,
        question_graph: QuestionGraph,
        path: SalesPathConfig | None = None,
    ) -> None:
        # Initialize as a QuestionnaireAgent (sets qg, policy, and default extractor)
        super().__init__(user_id, deps, question_graph)
        # Override extractor with domain alias to be explicit about intent
        self.extractor = SalesExtractor(deps.llm)
        self._path_graphs = path.graphs if path and path.graphs else {}
        self._path_settings = (
            path.settings
            if path and path.settings
            else {"lock_threshold": 2, "allow_switch_before_lock": True}
        )

    def _update_context_from_message(
        self, blob: AnswersBlob, message: InboundMessage
    ) -> AnswersBlob:
        # Determine active path via LLM selection (predicates removed)
        if not (blob.path_locked and blob.active_path):
            paths = list(self._path_graphs.keys())
            # Defer to extractor to ask LLM which path applies
            chosen = self.extractor.select_path(blob.answers, message.text or "", paths)
            if chosen:
                blob.active_path = chosen
                blob.path_locked = True
        return blob

    def _effective_graph(self, blob: AnswersBlob) -> QuestionGraph:  # type: ignore[override]
        if blob.active_path and blob.active_path in self._path_graphs:
            return self.qg.merge_with(self._path_graphs[blob.active_path])
        return self.qg

    def _save_blob(self, blob: AnswersBlob) -> None:
        self.deps.store.save(
            self.user_id,
            self.agent_type,
            blob.model_dump(),
        )
