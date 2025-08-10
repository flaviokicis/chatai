from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.tool_schemas import EscalateToHuman, UpdateAnswers

if TYPE_CHECKING:
    from app.core.llm import LLMClient

    from .question_graph import QuestionGraph


class QuestionnaireExtractor:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def extract(
        self, answers: dict[str, Any], pending_field: str | None, qg: QuestionGraph
    ) -> dict[str, Any]:
        tools: list[type[object]] = [UpdateAnswers, EscalateToHuman]
        summary = {k: answers.get(k) for k in qg}
        prompt = (
            "You update a structured checklist for a customer conversation. "
            "Be strictly conservative: extract a field only if the user's latest message EXPLICITLY provides it. "
            "Do not infer or guess. If uncertain, leave the field null.\n\n"
            f"Current known answers: {summary}\n"
            f"Previous question field key (may be null): {pending_field}\n"
            "Always respond by calling the UpdateAnswers tool with extracted values or EscalateToHuman when needed."
            "You need to EscalateToHuman if the conversation can't continue or if there's some kind of loop that cannot be resolved."
            "Feel free to EscalateToHuman if you feel like the customer is asking for or insisting on an information that is not available or not relevant to the specific goals of this conversation."
        )
        return self._llm.extract(prompt, tools)
