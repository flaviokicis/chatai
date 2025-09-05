from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from langfuse import get_client

from .llm import LLMClient

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


class LangChainToolsLLM(LLMClient):
    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat = chat_model

        self._langfuse = get_client()

    @property
    def model_name(self) -> str:
        """Get the model name from the underlying chat model."""
        # Try to extract model name from LangChain chat model
        if hasattr(self._chat, "model_name"):
            return self._chat.model_name
        if hasattr(self._chat, "model"):
            return self._chat.model
        if hasattr(self._chat, "_model_name"):
            return self._chat._model_name
        # Fallback: try to get from class name or other attributes
        class_name = self._chat.__class__.__name__
        if "Gemini" in class_name:
            return "gemini-2.5-flash"
        if "OpenAI" in class_name or "GPT" in class_name:
            return "gpt-4"
        return class_name

    def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
        # Start Langfuse generation with proper cost tracking
        generation = self._langfuse.start_observation(
            name="langchain_extract",
            as_type="generation",
            model=self.model_name,
            input=prompt,
            metadata={
                "operation": "tool_calling",
                "tools_available": [getattr(t, "__name__", str(t)) for t in tools],
                "tools_count": len(tools),
            }
        )

        try:
            with_tools = self._chat.bind_tools(tools)
            result = with_tools.invoke(prompt)

            content = getattr(result, "content", None)
            raw_calls: list[dict[str, Any]] = getattr(result, "tool_calls", [])

            # Extract token usage if available
            usage = getattr(result, "usage_metadata", None) or getattr(result, "response_metadata", {}).get("usage", {})

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

            # Update generation with output and usage data
            generation.update(
                output=content or json.dumps(out),
                usage={
                    "input_tokens": usage.get("input_tokens") or usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("output_tokens") or usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                } if usage else None,
                metadata={
                    "selected_tool": flat_args.get("__tool_name__") if calls else None,
                    "tools_called": len(calls),
                    "has_content": bool(content),
                }
            )
            generation.end()

            return out

        except Exception as e:
            generation.update(
                output=f"ERROR: {e}",
                metadata={"error": str(e), "error_type": type(e).__name__}
            )
            generation.end()
            raise


