from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid hard import at runtime
    from .llm import LLMClient


DEFAULT_INSTRUCTION = (
    "Rewrite the prompt into a single friendly question addressed to the user. "
    "Requirements: one sentence; no bullet points or lists; no multiple alternatives; "
    "no quotation marks; keep meaning; be concise."
)


def naturalize_prompt(llm: LLMClient, text: str, instruction: str | None = None) -> str:  # type: ignore[name-defined]
    instr = instruction or DEFAULT_INSTRUCTION
    try:
        rewritten = llm.rewrite(instr, text)
        if isinstance(rewritten, str) and rewritten.strip():
            # Defensive sanitization to ensure single-line question
            first_line = next((ln.strip() for ln in rewritten.splitlines() if ln.strip()), "")
            if first_line.startswith(("- ", "* ")):
                first_line = first_line[2:].strip()
            if first_line.startswith('"') and first_line.endswith('"') and len(first_line) > 1:
                first_line = first_line[1:-1].strip()
            return first_line or text
        return text
    except Exception:
        return text


def clarify_and_reask(llm: LLMClient, question_text: str, user_message: str) -> str:  # type: ignore[name-defined]
    """Produce a brief acknowledgement that references the user's clarification,
    then restate the original question as a single sentence.
    """
    instr = (
        "The user asked a clarification related to the question. "
        "Write a brief acknowledgement that references their wording, then restate the question succinctly. "
        "One sentence only; no lists; no quotes; keep meaning; be concise."
    )
    try:
        text = f"Question: {question_text}\nUser asked: {user_message}"
        rewritten = llm.rewrite(instr, text)
        if isinstance(rewritten, str) and rewritten.strip():
            first_line = next((ln.strip() for ln in rewritten.splitlines() if ln.strip()), "")
            if first_line.startswith(("- ", "* ")):
                first_line = first_line[2:].strip()
            if first_line.startswith('"') and first_line.endswith('"') and len(first_line) > 1:
                first_line = first_line[1:-1].strip()
            return first_line
        return question_text
    except Exception:
        return question_text
