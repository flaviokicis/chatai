from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgentDeps
from app.agents.sales_qualifier.factory import build_sales_qualifier_agent
from app.config.provider import AgentInstanceConfig
from app.core.llm import LLMClient
from app.core.messages import InboundMessage
from app.core.state import InMemoryStore
from app.services.human_handoff import LoggingHandoff


class DummyLLM(LLMClient):
    def __init__(self, args: dict[str, Any]) -> None:
        self._args = args

    def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
        return self._args


def test_build_question_graph_and_agent_handle() -> None:
    params = {
        "question_graph": [
            {"key": "intention", "prompt": "What is your intention?", "priority": 10},
            {
                "key": "is_sports_court_led",
                "prompt": "Is your intention to buy LED lights for a sports court?",
                "priority": 20,
            },
        ]
    }
    instance = AgentInstanceConfig(
        instance_id="sq1",
        agent_type="sales_qualifier",
        params=params,
        handoff={},
    )
    store = InMemoryStore()

    # First turn: LLM extracts the user's intention
    llm = DummyLLM(
        {
            "__tool_name__": "UpdateAnswers",
            "updates": {"intention": "buy leds"},
            "assistant_message": "Got it!",
        }
    )
    deps = BaseAgentDeps(store=store, llm=llm, handoff=LoggingHandoff())

    agent = build_sales_qualifier_agent("user-1", deps, instance)

    # First interaction - should ask the first question
    res1 = agent.handle(InboundMessage(user_id="user-1", text="hello", channel="test", metadata={}))
    assert res1.outbound is not None
    assert "what is your intention" in res1.outbound.text.lower()

    # Second interaction - user provides intention, should progress to next question
    res2 = agent.handle(
        InboundMessage(user_id="user-1", text="I want to buy LEDs", channel="test", metadata={})
    )
    assert res2.outbound is not None
    assert "sports court" in res2.outbound.text.lower()
