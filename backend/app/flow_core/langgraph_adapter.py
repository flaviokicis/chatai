from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    from langgraph.graph import StateGraph  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency for now
    StateGraph = None

from .compiler import CompiledFlow


def build_langgraph(compiled: CompiledFlow) -> Any:  # return type depends on langgraph
    if StateGraph is None:
        raise RuntimeError("langgraph is not installed")

    # Define state shape as a simple dict[str, Any]
    Graph = StateGraph(dict)

    def make_node_callable(node_id: str) -> Callable[[dict], dict]:
        def _node(state: dict) -> dict:
            state.setdefault("current_node_id", node_id)
            return state

        return _node

    for node_id in compiled.nodes:
        Graph.add_node(node_id, make_node_callable(node_id))

    # Add conditional edges
    for source, edges in compiled.edges_from.items():

        def chooser(state: dict) -> str:
            for e in edges:
                if e.guard_fn is None or e.guard_fn({**state, **e.guard_args}):
                    return e.target
            raise RuntimeError(f"No valid transition from {source}")

        mapping = {e.target: e.target for e in edges}
        Graph.add_conditional_edges(source, chooser, mapping)

    Graph.set_entry_point(compiled.entry)
    return Graph.compile()
