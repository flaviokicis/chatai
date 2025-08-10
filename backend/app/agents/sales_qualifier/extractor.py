from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.agents.common.questionnaire_extractor import QuestionnaireExtractor

if TYPE_CHECKING:
    from app.agents.common.question_graph import QuestionGraph
    from app.agents.common.state_types import AnswersState
    from app.core.llm import LLMClient


class SalesExtractor:
    def __init__(self, llm: LLMClient) -> None:
        self._impl = QuestionnaireExtractor(llm)

    def classify_and_update(
        self, state: AnswersState, message: str, question_graph: QuestionGraph
    ) -> dict[str, Any]:
        return self._impl.extract(state.answers, state.pending_field, question_graph)
