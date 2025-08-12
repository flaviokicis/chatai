from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid import cycles at runtime
    from app.core.llm import LLMClient
from .normalize import choose_option
from .tool_schemas import RequestHumanHandoff, UnknownAnswer, UpdateAnswersFlow


@dataclass(slots=True)
class Response:
    updates: dict[str, Any]
    escalate: bool = False
    reason: str | None = None
    tool_name: str | None = None


@dataclass(slots=True)
class ResponderContext:
    allowed_values: list[str] | None = None
    history: list[dict[str, str]] | None = None


class Responder:
    def respond(
        self,
        prompt_text: str,
        pending_field: str | None,
        answers: dict[str, Any],
        user_message: str,
        ctx: ResponderContext | None = None,
    ) -> Response:  # pragma: no cover - interface
        raise NotImplementedError


def _choose_from_allowed(user_message: str, allowed_values: list[str]) -> str | None:
    return choose_option(user_message, allowed_values)


class ManualResponder(Responder):
    def respond(
        self,
        prompt_text: str,
        pending_field: str | None,
        answers: dict[str, Any],
        user_message: str,
        ctx: ResponderContext | None = None,
    ) -> Response:
        allowed_values = ctx.allowed_values if ctx else None
        if pending_field:
            if allowed_values:
                chosen = _choose_from_allowed(user_message, allowed_values)
                if chosen is not None:
                    return Response(updates={pending_field: chosen}, tool_name="UpdateAnswersFlow")
            return Response(updates={pending_field: user_message}, tool_name="UpdateAnswersFlow")
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
        ctx: ResponderContext | None = None,
    ) -> Response:
        summary = {k: answers.get(k) for k in answers}
        # Include recent history (bounded) to give the model context
        history_lines: list[str] = []
        history = ctx.history if ctx else None
        if history:
            for msg in history[-10:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_lines.append(f"{role}: {content}")
        history_block = "\n".join(history_lines)

        instruction = (
            "Given the user's latest message and the current question, choose the best tool.\n"
            "Prefer UpdateAnswersFlow with a short value for the pending field if you can extract it.\n"
            "Use UnknownAnswer if the user doesn't know OR if the user asks a question about the prompt (clarification). "
            "Use RequestHumanHandoff only when necessary.\n\n"
            "Do NOT produce any assistant-facing messages; only choose a tool and its arguments.\n\n"
            f"Latest user message: {user_message}\n"
            f"Conversation window (oldest to newest):\n{history_block}\n\n"
            f"Question: {prompt_text}\n"
            f"Pending field: {pending_field}\n"
            f"Known answers: {summary}\n"
            f"User message: {user_message}\n"
            "Respond by calling exactly one tool and include ONLY the tool fields; do not include 'assistant_message'."
        )
        allowed_values = ctx.allowed_values if ctx else None
        if allowed_values and pending_field:
            instruction += (
                "\n\nWhen updating the pending field, you MUST choose a value exactly from this list: "
                f"{allowed_values}."
            )
        args = self._llm.extract(
            instruction, [UpdateAnswersFlow, UnknownAnswer, RequestHumanHandoff]
        )
        tool = args.get("__tool_name__") if isinstance(args, dict) else None
        # Fallback: accept bare {updates: {...}} without explicit tool name
        if tool is None and isinstance(args, dict) and isinstance(args.get("updates"), dict):
            tool = "UpdateAnswersFlow"
        # No assistant messages produced or consumed
        if tool == "UpdateAnswersFlow":
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
            )
        if tool == "UnknownAnswer":
            return Response(
                updates={},
                tool_name=tool,
            )
        if tool == "RequestHumanHandoff":
            return Response(
                updates={},
                escalate=True,
                reason=str(args.get("reason", "")),
                tool_name=tool,
            )
        return Response(
            updates={},
            tool_name=None,
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
        ctx: ResponderContext | None = None,
    ) -> Response:
        primary_res = self._primary.respond(prompt_text, pending_field, answers, user_message, ctx)
        # Do not fallback if the primary explicitly indicated an UnknownAnswer
        if primary_res.tool_name == "UnknownAnswer":
            return primary_res
        if (not primary_res.updates) and pending_field and user_message:
            # Fallback to manual value capture for the pending field
            return self._fallback.respond(prompt_text, pending_field, answers, user_message, ctx)
        return primary_res
