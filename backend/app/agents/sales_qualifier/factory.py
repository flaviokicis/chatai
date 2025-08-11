from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agents.base import BaseAgentDeps
    from app.config.provider import AgentInstanceConfig

from app.flow_core.builders import build_flow_from_question_graph_params, build_flow_from_questions
from app.flow_core.compiler import compile_flow

from .agent import SalesQualifierAgent


def build_compiled_flow(params: dict[str, Any], flow_id: str):
    flow = build_flow_from_question_graph_params(params, flow_id)
    return compile_flow(flow)


def _build_paths_and_settings(params: dict[str, Any]) -> tuple[dict[str, object], dict[str, Any]]:
    path_compiled: dict[str, object] = {}
    cfg = params.get("question_graph") if isinstance(params, dict) else None
    global_qs: list[dict[str, Any]] = []
    if isinstance(cfg, dict):
        g = cfg.get("global", [])
        if isinstance(g, list):
            global_qs = [q for q in g if isinstance(q, dict)]
        paths = cfg.get("paths", {})
        if isinstance(paths, dict):
            for name, section in paths.items():
                if not isinstance(section, dict):
                    continue
                path_qs = section.get("questions", [])
                if not isinstance(path_qs, list):
                    continue
                combined = [*global_qs, *[q for q in path_qs if isinstance(q, dict)]]
                flow = build_flow_from_questions(combined, flow_id=f"combined:{name}")
                path_compiled[str(name)] = compile_flow(flow)
    return path_compiled, {}


def build_sales_qualifier_agent(
    user_id: str, deps: BaseAgentDeps, instance: AgentInstanceConfig
) -> SalesQualifierAgent:
    params = instance.params or {}
    compiled = build_compiled_flow(params, flow_id=instance.instance_id or "sales")
    path_compiled, _unused = _build_paths_and_settings(params)
    return SalesQualifierAgent(user_id, deps, compiled_flow=compiled, path_compiled=path_compiled)
