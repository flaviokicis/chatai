from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.agents.common.questionnaire_extractor import QuestionnaireExtractor
from app.core.tool_schemas import SelectPath

if TYPE_CHECKING:
    from app.agents.common.question_graph import QuestionGraph
    from app.agents.common.state_types import AnswersState
    from app.core.llm import LLMClient


class SalesExtractor:
    def __init__(self, llm: LLMClient) -> None:
        self._impl = QuestionnaireExtractor(llm)
        self._llm = llm

    # Maintain same interface used by QuestionnaireAgent
    def extract(
        self,
        message_text: str,
        answers: dict[str, Any],
        pending_field: str | None,
        question_graph: QuestionGraph,
    ) -> dict[str, Any]:
        return self._impl.extract(message_text, answers, pending_field, question_graph)

    def classify_and_update(
        self, state: AnswersState, message: str, question_graph: QuestionGraph
    ) -> dict[str, Any]:
        return self._impl.extract(message, state.answers, state.pending_field, question_graph)

    def select_path(
        self, answers: dict[str, Any], message_text: str, paths: list[str]
    ) -> str | None:
        if not paths:
            return None
        summary = {k: answers.get(k) for k in answers}
        prompt = (
            "You decide which conversation path to follow based on the user's latest message and known answers.\n"
            "Be conservative. Choose a path ONLY if the message clearly indicates it. If uncertain, return null.\n\n"
            f"Latest user message: {message_text}\n"
            f"Known answers: {summary}\n"
            f"Available paths: {paths}\n"
            "Respond by calling SelectPath with 'path' as one of the available paths or null."
        )
        args = self._llm.extract(prompt, [SelectPath])
        chosen = args.get("path") if isinstance(args, dict) else None
        return chosen if isinstance(chosen, str) and chosen in paths else None
