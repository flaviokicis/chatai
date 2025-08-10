from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid import cycles at runtime
    from app.core.llm import LLMClient
from app.core.tool_schemas import EscalateToHuman, UnknownAnswer, UpdateAnswers


@dataclass(slots=True)
class Response:
    updates: dict[str, Any]
    escalate: bool = False
    reason: str | None = None
    tool_name: str | None = None
    assistant_message: str | None = None


class Responder:
    def respond(
        self,
        prompt_text: str,
        pending_field: str | None,
        answers: dict[str, Any],
        user_message: str,
        allowed_values: list[str] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> Response:  # pragma: no cover - interface
        raise NotImplementedError


def _choose_from_allowed(user_message: str, allowed_values: list[str]) -> str | None:
    text = " ".join(user_message.lower().split())
    best: tuple[int, str] | None = None
    for val in allowed_values:
        v = val.lower().replace("_", " ")
        score = 0
        if v in text:
            score += 3
        # token overlap
        v_tokens = [t for t in v.split() if t]
        match_tokens = sum(1 for t in v_tokens if t in text)
        score += match_tokens
        if score > 0 and (best is None or score > best[0]):
            best = (score, val)
    return best[1] if best else None


class ManualResponder(Responder):
    def respond(
        self,
        prompt_text: str,
        pending_field: str | None,
        answers: dict[str, Any],
        user_message: str,
        allowed_values: list[str] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> Response:
        if pending_field:
            if allowed_values:
                chosen = _choose_from_allowed(user_message, allowed_values)
                if chosen is not None:
                    return Response(updates={pending_field: chosen}, tool_name="UpdateAnswers")
            return Response(updates={pending_field: user_message}, tool_name="UpdateAnswers")
        return Response(updates={})


class LLMResponder(Responder):
    def __init__(self, llm: LLMClient) -> None:  # type: ignore[name-defined]
        self._llm = llm

    def _is_clarification(self, question_text: str, user_message: str) -> bool:
        try:
            instr = (
                "Decide if the user's message is requesting clarification of the question. "
                "Answer with a single token: yes or no."
            )
            payload = f"Question: {question_text}\nUser: {user_message}"
            ans = self._llm.rewrite(instr, payload)
            norm = (ans or "").strip().lower()
            return norm.startswith("y")
        except Exception:
            return False

    def respond(
        self,
        prompt_text: str,
        pending_field: str | None,
        answers: dict[str, Any],
        user_message: str,
        allowed_values: list[str] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> Response:
        summary = {k: answers.get(k) for k in answers}
        # Include recent history (bounded) to give the model context
        history_lines: list[str] = []
        if history:
            for msg in history[-10:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_lines.append(f"{role}: {content}")
        history_block = "\n".join(history_lines)

        instruction = (
            "Given the user's latest message and the current question, choose the best tool.\n"
            "Prefer UpdateAnswers with a short value for the pending field if you can extract it.\n"
            "Use UnknownAnswer if the user doesn't know OR if the user asks a question about the prompt (clarification). "
            "Use EscalateToHuman only when necessary.\n\n"
            "Also write the next assistant message to send to the user, acknowledging context when relevant, then restating or answering succinctly.\n\n"
            f"Conversation window (oldest to newest):\n{history_block}\n\n"
            f"Question: {prompt_text}\n"
            f"Pending field: {pending_field}\n"
            f"Known answers: {summary}\n"
            f"User message: {user_message}\n"
            "Respond by calling exactly one tool and include an 'assistant_message' field in tool args with the text to send."
        )
        if allowed_values and pending_field:
            instruction += (
                "\n\nWhen updating the pending field, you MUST choose a value exactly from this list: "
                f"{allowed_values}."
            )
        args = self._llm.extract(instruction, [UpdateAnswers, UnknownAnswer, EscalateToHuman])
        tool = args.get("__tool_name__") if isinstance(args, dict) else None
        assistant_message = args.get("assistant_message") if isinstance(args, dict) else None
        if tool == "UpdateAnswers":
            updates = args.get("updates") if isinstance(args, dict) else None
            if (
                isinstance(updates, dict)
                and pending_field
                and allowed_values
                and pending_field in updates
            ):
                raw = updates[pending_field]
                if isinstance(raw, str) and raw not in allowed_values:
                    chosen = _choose_from_allowed(raw, allowed_values)
                    if chosen is not None:
                        updates[pending_field] = chosen
            return Response(
                updates=updates if isinstance(updates, dict) else {},
                tool_name=tool,
                assistant_message=assistant_message if isinstance(assistant_message, str) else None,
            )
        if tool == "UnknownAnswer":
            return Response(
                updates={},
                tool_name=tool,
                assistant_message=assistant_message if isinstance(assistant_message, str) else None,
            )
        if tool == "EscalateToHuman":
            return Response(
                updates={},
                escalate=True,
                reason=str(args.get("reason", "")),
                tool_name=tool,
                assistant_message=assistant_message if isinstance(assistant_message, str) else None,
            )
        return Response(
            updates={},
            tool_name=None,
            assistant_message=assistant_message if isinstance(assistant_message, str) else None,
        )


class CompositeResponder(Responder):
    def __init__(self, primary: Responder, fallback: Responder) -> None:
        self._primary = primary
        self._fallback = fallback

    def respond(
        self,
        prompt_text: str,
        pending_field: str | None,
        answers: dict[str, Any],
        user_message: str,
        allowed_values: list[str] | None = None,
    ) -> Response:
        primary_res = self._primary.respond(
            prompt_text, pending_field, answers, user_message, allowed_values, history
        )
        # Do not fallback if the primary explicitly indicated an UnknownAnswer
        if primary_res.tool_name == "UnknownAnswer":
            return primary_res
        if (not primary_res.updates) and pending_field and user_message:
            # Fallback to manual value capture for the pending field
            return self._fallback.respond(
                prompt_text, pending_field, answers, user_message, allowed_values
            )
        return primary_res
