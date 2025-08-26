from typing import Any

from app.agents.flow_chat_agent import FlowChatAgent, ToolSpec
from app.core.llm import LLMClient


class SeqLLM(LLMClient):
    """Deterministic LLM returning pre-seeded results."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = results
        self._i = 0

    def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
        if self._i < len(self._results):
            res = self._results[self._i]
            self._i += 1
            return res
        return {}


def test_agent_executes_multiple_tool_calls() -> None:
    added: list[str] = []

    def add_node(node: str) -> str:
        added.append(node)
        return f"added {node}"

    tools = [ToolSpec(name="add", func=add_node)]
    llm = SeqLLM(
        [
            {"tool_calls": [{"name": "add", "arguments": {"node": "a"}}, {"name": "add", "arguments": {"node": "b"}}]},
            {"content": "done"},
        ]
    )
    agent = FlowChatAgent(llm=llm, tools=tools)
    history = [{"role": "user", "content": "add two nodes"}]
    response = agent.process({}, history)

    assert added == ["a", "b"]
    assert response.messages[-1] == "done"
