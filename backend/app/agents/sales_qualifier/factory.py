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
    # Build only the global graph; path-specific graphs will be selected at runtime
    return build_question_graph_from_params(params)


def _build_paths_and_settings(
    params: dict[str, Any],
) -> tuple[dict[str, QuestionGraph], dict[str, Any]]:
    path_graphs: dict[str, QuestionGraph] = {}

    cfg = params.get("question_graph") if isinstance(params, dict) else None
    if isinstance(cfg, dict):
        paths = cfg.get("paths", {})
        if isinstance(paths, dict):
            for name, section in paths.items():
                if not isinstance(section, dict):
                    continue
                questions = section.get("questions", [])
                path_graphs[str(name)] = build_question_graph_from_params(
                    {"question_graph": questions}
                )
    # Return empty settings for backward compatibility with caller signature
    return path_graphs, {}


def build_sales_qualifier_agent(
    user_id: str, deps: BaseAgentDeps, instance: AgentInstanceConfig
) -> SalesQualifierAgent:
    params = instance.params or {}
    qg = build_question_graph(params)
    path_graphs, _unused_settings = _build_paths_and_settings(params)
    path_cfg = SalesQualifierAgent.SalesPathConfig(
        graphs=path_graphs or None,
    )
    return SalesQualifierAgent(user_id, deps, qg, path=path_cfg)
