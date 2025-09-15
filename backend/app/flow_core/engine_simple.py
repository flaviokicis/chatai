"""Simplified flow engine - pure state machine without LLM decision-making."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .compiler import CompiledFlow

from .ir import DecisionNode, QuestionNode, TerminalNode
from .state import FlowContext, NodeStatus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StateSnapshot:
    """Current state of the flow."""

    current_node_id: str | None
    node_type: str | None  # "question", "decision", "terminal"
    node_data: dict[str, Any] | None = None
    available_edges: list[EdgeOption] | None = None
    is_complete: bool = False
    error: str | None = None


@dataclass(slots=True)
class EdgeOption:
    """An available navigation option."""

    target_node_id: str
    description: str | None = None
    condition: dict[str, Any] | None = None
    guard_satisfied: bool = True


@dataclass(slots=True)
class EngineState:
    """Engine response with current state and available options."""

    state: StateSnapshot
    prompt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SimpleFlowEngine:
    """
    Simplified flow engine that acts as a pure state machine.

    Key principles:
    1. No LLM decision-making - just tracks state
    2. Provides current state and available options
    3. Accepts navigation commands from external controller
    4. Validates transitions based on flow structure
    """

    def __init__(self, compiled: CompiledFlow) -> None:
        """Initialize the engine with a compiled flow."""
        self._flow = compiled

    def initialize_context(self, existing_context: FlowContext | None = None) -> FlowContext:
        """Initialize or restore flow context."""
        if existing_context:
            return existing_context

        ctx = FlowContext(flow_id=self._flow.id)
        ctx.current_node_id = self._flow.entry
        return ctx

    def get_state(
        self,
        ctx: FlowContext,
        user_message: str | None = None,
    ) -> EngineState:
        """
        Get current state and available options.

        This is the main entry point that:
        1. Returns the current node state
        2. Provides available navigation options
        3. Includes any relevant metadata
        """
        # Add user message to history if provided
        if user_message:
            ctx.add_turn("user", user_message, ctx.current_node_id)

        # Get current node
        node = self._get_current_node(ctx)
        if not node:
            return EngineState(
                state=StateSnapshot(
                    current_node_id=None,
                    node_type=None,
                    error="no_current_node",
                )
            )

        # Build state snapshot based on node type
        if isinstance(node, QuestionNode):
            return self._build_question_state(ctx, node)
        if isinstance(node, DecisionNode):
            return self._build_decision_state(ctx, node)
        if isinstance(node, TerminalNode):
            return self._build_terminal_state(ctx, node)

        return EngineState(
            state=StateSnapshot(
                current_node_id=node.id,
                node_type="unknown",
                error=f"unknown_node_type: {type(node).__name__}",
            )
        )

    def navigate_to(
        self,
        ctx: FlowContext,
        target_node_id: str,
        validate: bool = True,
    ) -> EngineState:
        """
        Navigate to a specific node.

        Args:
            ctx: Flow context
            target_node_id: Target node ID
            validate: Whether to validate the transition

        Returns:
            New engine state after navigation
        """
        if validate:
            # Check if target node exists
            if target_node_id not in self._flow.nodes:
                return EngineState(
                    state=StateSnapshot(
                        current_node_id=ctx.current_node_id,
                        node_type=None,
                        error=f"target_node_not_found: {target_node_id}",
                    )
                )

            # Check if transition is valid from current node
            current_edges = self._get_edges_from_node(ctx.current_node_id)
            valid_targets = {opt.target_node_id for opt in current_edges}

            # Allow navigation if it's a valid edge or if we're jumping to any question node
            target_node = self._flow.nodes[target_node_id]
            if target_node_id not in valid_targets and not isinstance(target_node, QuestionNode):
                # For non-question nodes, require valid edge
                return EngineState(
                    state=StateSnapshot(
                        current_node_id=ctx.current_node_id,
                        node_type=None,
                        error=f"invalid_transition: {ctx.current_node_id} -> {target_node_id}",
                    )
                )

        # Update context and get new state
        ctx.current_node_id = target_node_id
        return self.get_state(ctx)

    def update_answer(
        self,
        ctx: FlowContext,
        field: str,
        value: Any,
    ) -> None:
        """
        Update an answer in the context.

        This is a simple state update - no validation or navigation.
        """
        ctx.answers[field] = value

        # Mark current node as completed if it's a question node for this field
        node = self._get_current_node(ctx)
        if isinstance(node, QuestionNode) and node.key == field:
            ctx.get_node_state(node.id).status = NodeStatus.COMPLETED
            ctx.pending_field = None

    def advance_from_current(
        self,
        ctx: FlowContext,
    ) -> EngineState:
        """
        Advance from current node following default edges.

        This follows the first valid edge based on guards.
        """
        edges = self._get_edges_from_node(ctx.current_node_id)

        # Follow first valid edge
        for edge_opt in edges:
            if edge_opt.guard_satisfied:
                return self.navigate_to(ctx, edge_opt.target_node_id, validate=False)

        # No valid edge - stay on current node
        return self.get_state(ctx)

    def reset_context(self, ctx: FlowContext) -> None:
        """Reset context to initial state."""
        ctx.current_node_id = self._flow.entry
        ctx.answers.clear()
        ctx.node_states.clear()
        ctx.pending_field = None
        ctx.history.clear()
        ctx.turn_count = 0
        ctx.available_paths.clear()
        ctx.active_path = None
        ctx.path_confidence.clear()
        ctx.path_locked = False
        ctx.user_intent = None
        ctx.conversation_style = None
        ctx.clarification_count = 0
        ctx.is_complete = False
        ctx.escalation_reason = None

    # Private helper methods

    def _get_current_node(self, ctx: FlowContext) -> Any:
        """Get the current node from context."""
        if not ctx.current_node_id:
            return None
        return self._flow.nodes.get(ctx.current_node_id)

    def _get_edges_from_node(self, node_id: str | None) -> list[EdgeOption]:
        """Get available edges from a node."""
        if not node_id:
            return []

        edges = self._flow.edges_from.get(node_id, [])
        options = []

        for edge in edges:
            # Build edge option
            description = None
            if hasattr(edge, "condition_description"):
                description = str(edge.condition_description)
            elif hasattr(edge, "label"):
                description = str(edge.label)

            option = EdgeOption(
                target_node_id=edge.target,
                description=description,
                condition=getattr(edge, "guard_args", {}),
                guard_satisfied=True,  # Let external controller evaluate guards
            )
            options.append(option)

        return options

    def _build_question_state(self, ctx: FlowContext, node: QuestionNode) -> EngineState:
        """Build state for a question node."""
        ctx.mark_node_visited(node.id)
        ctx.pending_field = node.key

        # Get available navigation options
        edges = self._get_edges_from_node(node.id)

        # Check if question is already answered
        is_answered = node.key in ctx.answers and ctx.answers[node.key] not in (None, "")

        return EngineState(
            state=StateSnapshot(
                current_node_id=node.id,
                node_type="question",
                node_data={
                    "key": node.key,
                    "prompt": node.prompt,
                    "is_answered": is_answered,
                    "current_answer": ctx.answers.get(node.key),
                    "validator": getattr(node, "validator", None),
                    "meta": node.meta,
                },
                available_edges=edges,
            ),
            prompt=node.prompt,
            metadata={
                "visits": ctx.get_node_state(node.id).visits,
                "pending_field": node.key,
            },
        )

    def _build_decision_state(self, ctx: FlowContext, node: DecisionNode) -> EngineState:
        """Build state for a decision node."""
        ctx.mark_node_visited(node.id)
        ctx.pending_field = None

        # Get available edges with descriptions
        edges = self._get_edges_from_node(node.id)

        # Build path options for user choice
        path_options = []
        for edge in edges:
            if edge.description:
                # Extract path name from description
                path_name = edge.description
                if ":" in path_name:
                    path_name = path_name.split(":", 1)[1].strip()
                path_options.append(path_name)

        # Store available paths in context for reference
        ctx.available_paths = path_options

        return EngineState(
            state=StateSnapshot(
                current_node_id=node.id,
                node_type="decision",
                node_data={
                    "decision_type": getattr(node, "decision_type", "automatic"),
                    "decision_prompt": getattr(node, "decision_prompt", None),
                    "available_paths": path_options,
                },
                available_edges=edges,
            ),
            prompt=getattr(node, "decision_prompt", None),
            metadata={
                "needs_path_selection": True,
            },
        )

    def _build_terminal_state(self, ctx: FlowContext, node: TerminalNode) -> EngineState:
        """Build state for a terminal node."""
        ctx.mark_node_visited(node.id, NodeStatus.COMPLETED)
        ctx.is_complete = True

        return EngineState(
            state=StateSnapshot(
                current_node_id=node.id,
                node_type="terminal",
                node_data={
                    "reason": node.reason,
                    "final_answers": dict(ctx.answers),
                },
                is_complete=True,
            ),
            prompt=node.reason or "Conversa concluída",
            metadata={
                "final_answers": ctx.answers,
            },
        )
