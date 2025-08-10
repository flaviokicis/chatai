from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.tool_schemas import EscalateToHuman, UnknownAnswer, UpdateAnswers

if TYPE_CHECKING:
    from app.core.llm import LLMClient

    from .question_graph import QuestionGraph


class QuestionnaireExtractor:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def extract(
        self,
        message_text: str,
        answers: dict[str, Any],
        pending_field: str | None,
        qg: QuestionGraph,
    ) -> dict[str, Any]:
        tools: list[type[object]] = [UpdateAnswers, EscalateToHuman, UnknownAnswer]
        summary = {k: answers.get(k) for k in qg}
        allowed_keys = list(qg)
        prompt = (
            "You are a polite, gentle assistant that updates a structured checklist during a customer conversation. "
            "Be strictly conservative: extract a field only if the user's latest message EXPLICITLY provides it. "
            "Do not infer or guess. If uncertain, leave the field null unless the user explicitly expresses uncertainty.\n\n"
            f"Latest user message: {message_text}\n"
            f"Current known answers: {summary}\n"
            f"Valid keys you may update: {allowed_keys}\n"
            f"Previous question field key (may be null): {pending_field}\n"
            "Guidance:\n"
            "- If a previous question key is provided and the message answers it, update ONLY that key.\n"
            "- If the user clearly says they don't know / are unsure, call UnknownAnswer with the field name (or omit to apply to the pending field).\n"
            "- If a previous question key is provided and the user's message is a short, direct phrase (e.g., one to five words) and not a question, "
            "  assume it is the answer to the previous question and call UpdateAnswers with that key set to the user's phrase.\n"
            "- Otherwise, update ONLY the keys that the message explicitly answers. Never invent values.\n"
            "- Be courteous: avoid repetitive behavior; do not escalate for greetings or small talk.\n\n"
            "Escalation policy:\n"
            "- For greetings, small talk, or when no extractable info is present, DO NOT escalate. Return UpdateAnswers with empty 'updates'.\n"
            "- Escalate to a human ONLY when the conversation truly cannot proceed (e.g., user insists on unavailable info, safety issues, or irreconcilable conflict).\n\n"
            "Always respond by calling UpdateAnswers (with extracted values or with empty updates when nothing can be extracted), or UnknownAnswer when the user explicitly doesn't know, "
            "or EscalateToHuman only when strictly necessary."
        )
        return self._llm.extract(prompt, tools)
