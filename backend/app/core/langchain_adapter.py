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
    
    @property
    def model_name(self) -> str:
        """Get the model name from the underlying chat model."""
        # Try to extract model name from LangChain chat model
        if hasattr(self._chat, 'model_name'):
            return self._chat.model_name
        elif hasattr(self._chat, 'model'):
            return self._chat.model
        elif hasattr(self._chat, '_model_name'):
            return self._chat._model_name
        else:
            # Fallback: try to get from class name or other attributes
            class_name = self._chat.__class__.__name__
            if 'Gemini' in class_name:
                return 'gemini-2.5-flash'
            elif 'OpenAI' in class_name or 'GPT' in class_name:
                return 'gpt-4'
            else:
                return class_name

    def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
        with_tools = self._chat.bind_tools(tools)
        result = with_tools.invoke(prompt)

        content = getattr(result, "content", None)
        raw_calls: list[dict[str, Any]] = getattr(result, "tool_calls", [])

        calls: list[dict[str, Any]] = []
        for tc in raw_calls:
            name = tc.get("name")
            args_raw = tc.get("args", {}) or {}
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
            calls.append({"name": name, "arguments": args})

        out: dict[str, Any] = {"content": content, "tool_calls": calls}

        # Backwards compatibility: expose first tool call's args at top level
        if calls:
            chosen = None
            for name in ("UpdateAnswersFlow", "RequestHumanHandoff"):
                chosen = next((c for c in calls if c.get("name") == name), None)
                if chosen:
                    break
            if chosen is None:
                chosen = calls[0]
            flat_args = dict(chosen.get("arguments") or {})
            if "__tool_name__" not in flat_args:
                flat_args["__tool_name__"] = str(chosen.get("name", ""))
            out.update(flat_args)

        return out

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
