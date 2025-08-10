from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from langchain.chat_models import init_chat_model

from .llm import LLMClient

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


class LangChainToolsLLM(LLMClient):
    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat = chat_model
        self._rewrite_chat = None  # lazy-inited lightweight model for rewrite

    def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
        with_tools = self._chat.bind_tools(tools)
        result = with_tools.invoke(prompt)
        tool_calls: list[dict[str, Any]] = getattr(result, "tool_calls", [])
        if not tool_calls:
            return {}

        chosen = None
        for name in ("UpdateAnswers", "EscalateToHuman"):
            chosen = next((tc for tc in tool_calls if tc.get("name") == name), None)
            if chosen:
                break
        if chosen is None:
            chosen = tool_calls[0]
        args_raw = chosen.get("args", {}) or {}
        args: dict[str, Any] | None
        if isinstance(args_raw, str):
            try:
                parsed = json.loads(args_raw)
                args = parsed if isinstance(parsed, dict) else {}
            except Exception:
                args = {}
        elif isinstance(args_raw, dict):
            args = args_raw
        else:
            args = {}

        if "__tool_name__" not in args:
            args["__tool_name__"] = str(chosen.get("name", ""))
        return args

    def rewrite(self, instruction: str, text: str) -> str:  # type: ignore[override]
        try:
            # Use a cheaper model for style rewriting
            if self._rewrite_chat is None:
                self._rewrite_chat = init_chat_model(
                    "gemini-2.5-flash-lite", model_provider="google_genai"
                )

            prompt = (
                f"Instruction: {instruction}\n"
                f"Original: {text}\n"
                "Rewrite naturally as a friendly human attendant. Keep the meaning, vary wording slightly, and avoid repetition."
            )
            result = self._rewrite_chat.invoke(prompt)
            content = getattr(result, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
            # Fallback to original if model returns nothing structured
            return text
        except Exception:
            return text
