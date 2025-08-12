from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid hard import at runtime
    from .llm import LLMClient

# Human pacing defaults for multi-message outputs
MIN_FOLLOWUP_DELAY_MS = 2200
MAX_FOLLOWUP_DELAY_MS = 4000
MAX_MULTI_MESSAGES = 8

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


def rewrite_whatsapp_multi(
    llm: LLMClient,  # type: ignore[name-defined]
    original_text: str,
    chat_window: list[dict[str, str]] | None = None,
    *,
    max_followups: int = 2,
) -> list[dict[str, int | str]]:
    """Rewrite an assistant reply into human-like WhatsApp-style messages.

    Returns a list of {"text": str, "delay_ms": int} objects. The first message should have
    delay_ms=0. Follow-ups should be paced to feel human.

    If rewriting fails, returns a single message with original_text.
    """
    if not original_text.strip():
        return [{"text": original_text, "delay_ms": 0}]

    history_lines: list[str] = []
    last_user_message: str = ""
    for turn in chat_window or []:
        role = (turn.get("role") or "").strip()
        content = (turn.get("content") or "").strip()
        if role and content:
            history_lines.append(f"{role}: {content}")
            if role.lower() == "user":
                last_user_message = content

    history_block = "\n".join(history_lines[-200:])  # cap to keep prompt bounded

    instruction = (
        "Role: You are a warm, friendly receptionist on WhatsApp.\n"
        "Task: Rewrite the assistant's reply into short, human-like messages.\n"
        "You decide how many messages to send (one is fine; often two is great).\n\n"
        "CRITICAL CONSTRAINTS (must-follow):\n"
        "- Preserve the original meaning EXACTLY. Do NOT change the topic or add new details.\n"
        "- If the original includes choices/entities/units/numbers, reproduce them VERBATIM (same wording, same order).\n"
        "- Do NOT turn the prompt into a different question. Only rephrase tone and split across bubbles.\n\n"
        "- Do NOT introduce words like 'revisit' or 'Let's revisit' unless they already appear in the original text.\n\n"
        "Style guidelines:\n"
        "- If the user just answered or corrected something, begin with a brief acknowledgement that references it.\n"
        "- Keep it friendly and succinct; plain text only.\n"
        "- Use a tiny transition only when it truly helps the flow; avoid filler.\n"
        "- Keep each message <= 120 characters.\n"
        "- Timing: first message delay_ms = 0; subsequent messages 2200-4000 ms.\n"
        "- Output STRICTLY a JSON array of {text: string, delay_ms: integer}.\n\n"
        "If you cannot keep every original choice/entity exactly as written, return a SINGLE message with the original text and delay_ms = 0.\n\n"
        "Examples (format only, content must remain unchanged):\n"
        "Input: 'Could you tell me if it's more like a tennis court or a soccer field?'\n"
        'Output: [\n  {"text": "Got it!", "delay_ms": 0},\n  {"text": "Is it more like a tennis court or a soccer field?", "delay_ms": 1600}\n]\n\n'
        "Input: 'What can I help you with today?'\n"
        'Output: [\n  {"text": "What can I help you with today?", "delay_ms": 0}\n]\n'
    )

    payload = (
        f"Original assistant reply:\n{original_text}\n\n"
        f"Latest user message (if any):\n{last_user_message}\n\n"
        f"Conversation window (oldest to newest):\n{history_block}"
    )

    try:
        raw = llm.rewrite(instruction, payload)
        # Try to parse JSON array
        import json

        messages = json.loads(raw) if isinstance(raw, str) else []
        out: list[dict[str, int | str]] = []
        if isinstance(messages, list):
            for i, item in enumerate(messages):
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                try:
                    delay_ms_val = int(item.get("delay_ms", 0))
                except Exception:
                    delay_ms_val = 0 if i == 0 else MIN_FOLLOWUP_DELAY_MS
                if i == 0:
                    delay_ms_val = 0
                out.append({"text": text, "delay_ms": max(0, delay_ms_val)})
                # Soft cap to prevent pathological outputs; keep generous to feel free-form
                if len(out) >= MAX_MULTI_MESSAGES:
                    break
        if out:
            # Normalize follow-up delays into human pacing range
            for idx in range(1, len(out)):
                try:
                    d = int(out[idx].get("delay_ms", MIN_FOLLOWUP_DELAY_MS))
                except Exception:
                    d = MIN_FOLLOWUP_DELAY_MS
                if d < MIN_FOLLOWUP_DELAY_MS:
                    d = MIN_FOLLOWUP_DELAY_MS
                elif d > MAX_FOLLOWUP_DELAY_MS:
                    d = MAX_FOLLOWUP_DELAY_MS
                out[idx]["delay_ms"] = d
            return out
    except Exception:
        # Fall back to simple single-message naturalization
        pass

    # Fallback: single naturalized message
    try:
        first = naturalize_prompt(llm, original_text)
    except Exception:
        first = original_text
    return [{"text": first, "delay_ms": 0}]
