from __future__ import annotations

from typing import Any

from .ir import DecisionNode, Edge, Flow, GuardRef, QuestionNode, TerminalNode


def build_flow_from_questions(questions: list[dict[str, Any]], flow_id: str) -> Flow:
    """Build a simple questionnaire-style Flow from question dicts.

    Each item requires keys: {key: str, prompt: str, priority?: int, dependencies?: list[str]}.
    """
    chooser = DecisionNode(id="choose_next", label="choose_next")
    terminal = TerminalNode(id="done", label="done", reason="checklist_complete")
    nodes: list[Any] = [chooser, terminal]

    normalized: list[dict[str, Any]] = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        prompt = str(item.get("prompt", "")).strip()
        if not key or not prompt:
            continue
        priority = int(item.get("priority", 100))
        deps_raw = item.get("dependencies", [])
        deps = [str(d) for d in deps_raw] if isinstance(deps_raw, list) else []
        normalized.append(
            {"key": key, "prompt": prompt, "priority": priority, "dependencies": deps}
        )

    # Question nodes
    for q in normalized:
        nodes.append(
            QuestionNode(id=f"q:{q['key']}", label=q["key"], key=q["key"], prompt=q["prompt"])
        )

    # Edges
    edges: list[Edge] = []
    for q in sorted(normalized, key=lambda it: it["priority"]):
        guard = GuardRef(
            fn="deps_missing", args={"key": q["key"], "dependencies": list(q["dependencies"])}
        )
        edges.append(
            Edge(source=chooser.id, target=f"q:{q['key']}", guard=guard, priority=q["priority"])
        )

    edges.append(
        Edge(source=chooser.id, target=terminal.id, guard=GuardRef(fn="always"), priority=10_000)
    )
    for q in normalized:
        edges.append(
            Edge(source=f"q:{q['key']}", target=chooser.id, guard=GuardRef(fn="always"), priority=0)
        )

    return Flow(id=flow_id, entry=chooser.id, nodes=nodes, edges=edges)


def build_flow_from_question_graph_params(params: dict[str, Any], flow_id: str) -> Flow:
    """Compatibility builder: accept the prior `question_graph` config shape and build Flow.

    Supported shapes:
    - { question_graph: [ {key,prompt,priority,dependencies?}, ... ] }
    - { question_graph: { global: [...], paths?: {...} } }  -> only 'global' is used here.
    """
    cfg = params.get("question_graph") if isinstance(params, dict) else None
    if isinstance(cfg, dict) and ("global" in cfg or "paths" in cfg):
        questions = cfg.get("global", [])
        return build_flow_from_questions(questions if isinstance(questions, list) else [], flow_id)
    if isinstance(cfg, list):
        return build_flow_from_questions(cfg, flow_id)
    # If already given as Flow IR under key 'flow', validate via model
    flow_raw = params.get("flow") if isinstance(params, dict) else None
    if isinstance(flow_raw, dict):
        return Flow.model_validate(flow_raw)  # type: ignore[no-any-return]
    # Fallback to empty flow
    return build_flow_from_questions([], flow_id)
