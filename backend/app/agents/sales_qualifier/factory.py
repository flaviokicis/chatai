from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agents.base import BaseAgentDeps
    from app.config.provider import AgentInstanceConfig

from app.agents.common.question_graph import (
    QuestionGraph,
    build_question_graph_from_params,
)

from .agent import SalesQualifierAgent


def build_question_graph(params: dict[str, Any]) -> QuestionGraph:
    return build_question_graph_from_params(params)


def build_sales_qualifier_agent(
    user_id: str, deps: BaseAgentDeps, instance: AgentInstanceConfig
) -> SalesQualifierAgent:
    qg = build_question_graph(instance.params or {})
    return SalesQualifierAgent(user_id, deps, qg)
