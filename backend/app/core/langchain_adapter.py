from __future__ import annotations

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
        args = chosen.get("args", {}) or {}
        if isinstance(args, dict) and "__tool_name__" not in args:
            args["__tool_name__"] = str(chosen.get("name", ""))
        return args if isinstance(args, dict) else {}
