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
    settings: dict[str, Any] = {"lock_threshold": 1, "allow_switch_before_lock": True}

    cfg = params.get("question_graph") if isinstance(params, dict) else None
    if isinstance(cfg, dict):
        sel = cfg.get("path_selection")
        if isinstance(sel, dict):
            if isinstance(sel.get("lock_threshold"), int):
                settings["lock_threshold"] = int(sel["lock_threshold"])  # type: ignore[index]
            if isinstance(sel.get("allow_switch_before_lock"), bool):
                settings["allow_switch_before_lock"] = bool(sel["allow_switch_before_lock"])  # type: ignore[index]

        paths = cfg.get("paths", {})
        if isinstance(paths, dict):
            for name, section in paths.items():
                if not isinstance(section, dict):
                    continue
                # Build path graph from questions
                questions = section.get("questions", [])
                path_graphs[str(name)] = build_question_graph_from_params(
                    {"question_graph": questions}
                )
    return path_graphs, settings


def build_sales_qualifier_agent(
    user_id: str, deps: BaseAgentDeps, instance: AgentInstanceConfig
) -> SalesQualifierAgent:
    params = instance.params or {}
    qg = build_question_graph(params)
    path_graphs, path_settings = _build_paths_and_settings(params)
    path_cfg = SalesQualifierAgent.SalesPathConfig(
        graphs=path_graphs or None,
        settings=path_settings or None,
    )
    return SalesQualifierAgent(user_id, deps, qg, path=path_cfg)
