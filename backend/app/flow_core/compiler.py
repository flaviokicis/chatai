from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .guards import DEFAULT_GUARDS, GuardFunction
from .ir import Flow, GuardRef, Node


class CompiledEdge(BaseModel):
    source: str
    target: str
    guard_fn: GuardFunction | None = None
    guard_args: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0


class CompiledFlow(BaseModel):
    id: str
    entry: str
    nodes: dict[str, Node]
    edges_from: dict[str, list[CompiledEdge]]


def _compile_guard(ref: GuardRef | None) -> tuple[GuardFunction | None, dict[str, Any]]:
    if ref is None:
        return None, {}
    fn = DEFAULT_GUARDS.get(ref.fn)
    return fn, dict(ref.args)


def compile_flow(flow: Flow) -> CompiledFlow:
    # Validate entry node exists
    if flow.node_by_id(flow.entry) is None:
        raise ValueError(f"entry node '{flow.entry}' not found")

    node_map: dict[str, Node] = {n.id: n for n in flow.nodes}
    edges_from: dict[str, list[CompiledEdge]] = {}

    for e in flow.edges:
        if e.source not in node_map:
            raise ValueError(f"edge source '{e.source}' not found")
        if e.target not in node_map:
            raise ValueError(f"edge target '{e.target}' not found")
        guard_fn, guard_args = _compile_guard(e.guard)
        edges_from.setdefault(e.source, []).append(
            CompiledEdge(
                source=e.source,
                target=e.target,
                guard_fn=guard_fn,
                guard_args=guard_args,
                priority=e.priority,
            )
        )

    # Sort edges by priority ascending to provide deterministic ordering
    for src, lst in edges_from.items():
        lst.sort(key=lambda ce: ce.priority)

    return CompiledFlow(id=flow.id, entry=flow.entry, nodes=node_map, edges_from=edges_from)
