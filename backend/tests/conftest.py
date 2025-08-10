from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import pytest

from app.agents.base import BaseAgentDeps
from app.agents.common.question_graph import Question, QuestionGraph
from app.agents.common.questionnaire_agent import QuestionnaireAgent
from app.core.llm import LLMClient
from app.core.state import InMemoryStore
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
def question_graph() -> QuestionGraph:
    return QuestionGraph(
        [
            Question(key="a", prompt="Ask A?", priority=10),
            Question(key="b", prompt="Ask B?", priority=20, dependencies=["a"]),
        ]
    )


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def handoff() -> LoggingHandoff:
    return LoggingHandoff()


@pytest.fixture
def make_agent(
    store: InMemoryStore, handoff: LoggingHandoff, question_graph: QuestionGraph
) -> Callable[[list[dict[str, Any]]], QuestionnaireAgent]:
    def _make(results: list[dict[str, Any]]) -> QuestionnaireAgent:
        llm = SeqLLM(results)
        deps = BaseAgentDeps(store=store, llm=llm, handoff=handoff)
        return QuestionnaireAgent("u", deps, question_graph)

    return _make
