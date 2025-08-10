from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .compiler import CompiledFlow
from .ir import DecisionNode, QuestionNode, TerminalNode


@dataclass(slots=True)
class FlowState:
    flow_id: str
    current_node_id: str | None = None
    answers: dict[str, Any] = field(default_factory=dict)
    pending_field: str | None = None
    # Path policy state (optional use)
    path_votes: dict[str, int] = field(default_factory=dict)
    active_path: str | None = None
    path_locked: bool = False


@dataclass(slots=True)
class EngineOutcome:
    kind: Literal["prompt", "terminal"]
    message: str | None
    node_id: str


class Engine:
    def __init__(self, compiled: CompiledFlow) -> None:
        self._c = compiled

    def start(self) -> FlowState:
        return FlowState(flow_id=self._c.id, current_node_id=self._c.entry)

    def step(self, state: FlowState, event: dict[str, Any] | None = None) -> EngineOutcome:
        node = self._c.nodes[state.current_node_id] if state.current_node_id else None
        if node is None:
            raise RuntimeError("Engine has no current node")

        # Handle node kinds
        if isinstance(node, QuestionNode):
            state.pending_field = node.key
            # If the last tool indicated clarification (UnknownAnswer) and no answer provided, stay
            if (
                event is not None
                and event.get("tool_name") == "UnknownAnswer"
                and "answer" not in event
            ):
                return EngineOutcome(kind="prompt", message=node.prompt, node_id=node.id)
            # If an answer is provided, store it and attempt to advance
            if event is not None and "answer" in event:
                state.answers[node.key] = event.get("answer")
                # If there are no guarded edges from this question, fall through to a decision node
                edges = self._c.edges_from.get(node.id, [])
                if not edges:
                    # Find an implicit decision by following from entry start, else re-prompt
                    # Simplicity: re-prompt when there's no outgoing edges
                    return EngineOutcome(kind="prompt", message=node.prompt, node_id=node.id)
                for e in edges:
                    ctx = self._build_guard_context(state, event, e.guard_args)
                    chosen = bool(e.guard_fn(ctx)) if e.guard_fn is not None else True
                    if chosen:
                        state.current_node_id = e.target
                        # Consume the answer event after applying it to this question
                        return self.step(state, None)
                # If no transition, stay and prompt again
            return EngineOutcome(kind="prompt", message=node.prompt, node_id=node.id)

        if isinstance(node, TerminalNode):
            return EngineOutcome(kind="terminal", message=node.reason or "done", node_id=node.id)

        if isinstance(node, DecisionNode):
            # Evaluate outgoing edges by priority and first true guard
            edges = self._c.edges_from.get(node.id, [])
            for e in edges:
                if e.guard_fn is None:
                    chosen = True
                else:
                    ctx = self._build_guard_context(state, event, e.guard_args)
                    chosen = bool(e.guard_fn(ctx))
                if chosen:
                    state.current_node_id = e.target
                    # Do not propagate prior answer events beyond a decision hop
                    return self.step(state, None)  # tail-call to process next node
            # If no edge matched, this is a dead end
            raise RuntimeError(f"No valid transition from decision node '{node.id}'")

        raise RuntimeError(f"Unsupported node kind: {type(node).__name__}")

    @staticmethod
    def _build_guard_context(
        state: FlowState, event: dict[str, Any] | None, extra: dict[str, Any]
    ) -> dict[str, Any]:
        ctx = {
            "answers": state.answers,
            "pending_field": state.pending_field,
            "active_path": state.active_path,
            "path_locked": state.path_locked,
            "event": event or {},
        }
        ctx.update(extra)
        return ctx
