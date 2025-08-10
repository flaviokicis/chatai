from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .llm import LLMClient

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


class LangChainToolsLLM(LLMClient):
    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat = chat_model

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
