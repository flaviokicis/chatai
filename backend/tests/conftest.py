from __future__ import annotations

from typing import Any

import pytest

from app.agents.base import BaseAgentDeps, FlowAgent
from app.core.llm import LLMClient
from app.core.state import InMemoryStore
from app.flow_core.builders import build_flow_from_questions
from app.flow_core.compiler import compile_flow
from app.services.human_handoff import LoggingHandoff


class SeqLLM(LLMClient):
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = results
        self._i = 0

    def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
        if self._i < len(self._results):
            res = self._results[self._i]
            self._i += 1
            return res
        return {}


@pytest.fixture
def compiled_flow():
    flow = build_flow_from_questions(
        [
            {"key": "a", "prompt": "Ask A?", "priority": 10},
            {"key": "b", "prompt": "Ask B?", "priority": 20, "dependencies": ["a"]},
        ],
        flow_id="test",
    )
    return compile_flow(flow)


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def handoff() -> LoggingHandoff:
    return LoggingHandoff()


@pytest.fixture
def make_agent(store: InMemoryStore, handoff: LoggingHandoff, compiled_flow):
    def _make(results: list[dict[str, Any]]):
        llm = SeqLLM(results)
        deps = BaseAgentDeps(store=store, llm=llm, handoff=handoff)
        return FlowAgent("u", deps, compiled_flow=compiled_flow)

    return _make



