from __future__ import annotations

from typing import Any, Callable, Sequence

from pydantic import BaseModel

from app.core.llm import LLMClient


class ToolSpec(BaseModel):
    """Specification for a callable tool."""

    name: str
    description: str | None = None
    args_schema: type[BaseModel] | None = None
    func: Callable[..., str]


class FlowChatAgent:
    """LLM-driven agent that can apply tools to modify a flow."""

    def __init__(self, llm: LLMClient, tools: Sequence[ToolSpec] | None = None) -> None:
        self.llm = llm
        self.tools = {t.name: t for t in tools or []}

    def process(self, flow: dict[str, Any], history: Sequence[dict[str, str]]) -> list[str]:
        """Process conversation and return assistant responses."""

        messages = list(history)
        outputs: list[str] = []
        tool_schemas = [t.args_schema for t in self.tools.values() if t.args_schema]
        # Simple loop allowing multiple tool invocations
        for _ in range(10):  # hard limit to avoid infinite loops
            prompt = self._build_prompt(flow, messages)
            result = self.llm.extract(prompt, tool_schemas)
            content = result.get("content")
            if content:
                outputs.append(content)
                messages.append({"role": "assistant", "content": content})
            tool_calls = result.get("tool_calls") or []
            if not tool_calls:
                break
            for call in tool_calls:
                name = call.get("name")
                args = call.get("arguments", {})
                tool = self.tools.get(name)
                if not tool:
                    continue
                tool_output = tool.func(**args)
                outputs.append(tool_output)
                messages.append({"role": "assistant", "content": tool_output})
        return outputs

    def _build_prompt(self, flow: dict[str, Any], history: Sequence[dict[str, str]]) -> str:
        """Very small prompt builder combining flow and chat history."""

        lines = ["You are a flow editing assistant."]
        lines.append(f"Current flow: {flow}")
        for m in history:
            lines.append(f"{m['role']}: {m['content']}")
        return "\n".join(lines)
