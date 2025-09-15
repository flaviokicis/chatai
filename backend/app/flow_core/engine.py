"""Simplified flow engine - pure state machine without LLM decision-making."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

    from .compiler import CompiledFlow

from .ir import DecisionNode, QuestionNode, TerminalNode
from .state import FlowContext, NodeStatus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EngineResponse:
    """Response from the engine after processing."""

    kind: Literal["prompt", "terminal", "escalate"]
    message: str | None
    node_id: str | None
    metadata: dict[str, Any] | None = None
    suggested_actions: list[str] | None = None


class LLMFlowEngine:
    """
    Simplified flow engine that acts as a pure state machine.

    Key principles:
    1. No LLM decision-making - just tracks state
    2. Provides current state and available navigation
    3. External controller (GPT-5) makes all decisions
    4. Engine only validates and executes transitions
    """

    def __init__(
        self,
        compiled: CompiledFlow,
        llm: LLMClient | None = None,  # Keep for compatibility but unused
        *,
        strict_mode: bool = False,
    ) -> None:
        """Initialize the engine with a compiled flow."""
        self._flow = compiled
        self._llm = llm  # Kept for compatibility but not used
        self._strict_mode = strict_mode

    def initialize_context(self, existing_context: FlowContext | None = None) -> FlowContext:
        """Initialize or restore flow context."""
        if existing_context:
            return existing_context

        ctx = FlowContext(flow_id=self._flow.id)
        ctx.current_node_id = self._flow.entry
        return ctx

    def process(
        self,
        ctx: FlowContext,
        user_message: str | None = None,
        event: dict[str, Any] | None = None,
        project_context: ProjectContext | None = None,
    ) -> EngineResponse:
        """Process a turn in the conversation - simplified state machine."""
        # Add user message to history if provided
        if user_message:
            ctx.add_turn("user", user_message, ctx.current_node_id)

        # Get current node
        node = self._get_current_node(ctx)
        if not node:
            return self._handle_no_node(ctx)

        # Process based on node type
        if isinstance(node, QuestionNode):
            return self._process_question_node(ctx, node, user_message, event, project_context)
        if isinstance(node, DecisionNode):
            return self._process_decision_node(ctx, node, event, project_context)
        if isinstance(node, TerminalNode):
            return self._process_terminal_node(ctx, node)

        logger.warning(f"Unknown node type: {type(node).__name__}")
        return EngineResponse(
            kind="escalate",
            message="Encontrei uma situação inesperada. Vou chamar alguém para ajudar.",
            node_id=node.id if node else None,
            metadata={"error": f"unknown_node_type: {type(node).__name__}"},
        )

    def _process_question_node(
        self,
        ctx: FlowContext,
        node: QuestionNode,
        user_message: str | None,
        event: dict[str, Any] | None,
        project_context: ProjectContext | None = None,
    ) -> EngineResponse:
        """Process a question node."""
        ctx.mark_node_visited(node.id)
        ctx.pending_field = node.key

        # If we have an event with navigation, handle it
        if event:
            # Handle navigation events
            if "target_node_id" in event:
                target = event["target_node_id"]
                if target and target in self._flow.nodes:
                    ctx.current_node_id = target
                    return self.process(ctx, None, None, project_context)

            # Handle answer events
            if "answer" in event:
                answer = event["answer"]
                ctx.answers[node.key] = answer
                ctx.get_node_state(node.id).status = NodeStatus.COMPLETED
                return self._advance_from_node(ctx, node, project_context)

            # Handle tool events
            tool_name = event.get("tool_name")
            if tool_name == "RestartConversation":
                # This is now handled by PerformAction with "restart" action
                return self._handle_restart(ctx, project_context)
            if tool_name == "RequestHumanHandoff":
                return EngineResponse(
                    kind="escalate",
                    message="Transferindo você para um atendente humano.",
                    node_id=node.id,
                    metadata={"reason": event.get("reason", "requested")},
                )

        # Get available edges for navigation
        edges = self._get_edges_from_node(node.id)
        edge_info = []
        for edge in edges:
            edge_info.append(
                {
                    "target_node_id": edge.target,
                    "description": self._get_edge_description(edge),
                }
            )

        # Return prompt with navigation options
        return EngineResponse(
            kind="prompt",
            message=node.prompt,
            node_id=node.id,
            metadata={
                "pending_field": node.key,
                "available_edges": edge_info,
            },
            suggested_actions=self._suggest_actions(node, ctx),
        )

    def _process_decision_node(
        self,
        ctx: FlowContext,
        node: DecisionNode,
        event: dict[str, Any] | None,
        project_context: ProjectContext | None = None,
    ) -> EngineResponse:
        """Process a decision node."""
        ctx.mark_node_visited(node.id)
        ctx.pending_field = None

        # Get edges from this node
        edges = self._get_edges_from_node(node.id)
        if not edges:
            return self._handle_dead_end(ctx, node)

        # Build available paths
        path_options = []
        edge_info = []
        for edge in edges:
            description = self._get_edge_description(edge)
            path_name = description
            if ":" in description:
                path_name = description.split(":", 1)[1].strip()
            path_options.append(path_name)
            edge_info.append(
                {
                    "target_node_id": edge.target,
                    "description": description,
                    "path_name": path_name,
                }
            )

        ctx.available_paths = path_options

        # If we have a navigation event, process it
        if event and "target_node_id" in event:
            target = event["target_node_id"]
            if target and target in self._flow.nodes:
                ctx.current_node_id = target
                return self.process(ctx, None, None, project_context)

        # For automatic decisions, still present options to GPT-5 for consistency
        # GPT-5 will make the routing decision via PerformAction with navigate action
        decision_type = getattr(node, "decision_type", "automatic")

        # Return decision prompt with options
        return EngineResponse(
            kind="prompt",
            message=getattr(node, "decision_prompt", None)
            or self._generate_decision_prompt(node, path_options),
            node_id=node.id,
            metadata={
                "needs_path_selection": True,
                "available_paths": path_options,
                "available_edges": edge_info,
            },
        )

    def _process_terminal_node(
        self,
        ctx: FlowContext,
        node: TerminalNode,
    ) -> EngineResponse:
        """Process a terminal node."""
        ctx.mark_node_visited(node.id, NodeStatus.COMPLETED)
        ctx.is_complete = True

        return EngineResponse(
            kind="terminal",
            message=node.reason or "Conversa concluída",
            node_id=node.id,
            metadata={"final_answers": ctx.answers},
        )

    def _advance_from_node(
        self,
        ctx: FlowContext,
        node: Any,
        project_context: ProjectContext | None = None,
    ) -> EngineResponse:
        """Advance from current node to next."""
        edges = self._get_edges_from_node(node.id)

        if not edges:
            # No outgoing edges, find next question or complete
            return self._find_next_question(ctx, project_context)

        # Follow first edge (no guard evaluation in simplified version)
        ctx.current_node_id = edges[0].target
        return self.process(ctx, None, None, project_context)

    def _find_next_question(
        self,
        ctx: FlowContext,
        project_context: ProjectContext | None = None,
    ) -> EngineResponse:
        """Find the next unanswered question."""
        unanswered = self._get_unanswered_questions(ctx)
        if not unanswered:
            ctx.is_complete = True
            return EngineResponse(
                kind="terminal",
                message="Todas as perguntas foram respondidas. Obrigado!",
                node_id=ctx.current_node_id,
            )

        # Pick first unanswered question
        next_q = unanswered[0]
        ctx.current_node_id = next_q["id"]
        return self.process(ctx, None, None, project_context)

    def _handle_restart(
        self,
        ctx: FlowContext,
        project_context: ProjectContext | None = None,
    ) -> EngineResponse:
        """Handle conversation restart."""
        # Reset context
        entry_node_id = self._flow.entry
        ctx.current_node_id = entry_node_id
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

        # Process from entry
        return self.process(ctx, None, None, project_context)

    # Helper methods

    def _get_current_node(self, ctx: FlowContext) -> Any:
        """Get the current node from context."""
        if not ctx.current_node_id:
            return None
        node = self._flow.nodes.get(ctx.current_node_id)

        # Ensure pending_field is synchronized with current question node
        if (
            node
            and hasattr(node, "key")
            and hasattr(node, "__class__")
            and node.__class__.__name__ == "QuestionNode"
        ):
            if ctx.pending_field != node.key:
                ctx.pending_field = node.key

        return node

    def _get_edges_from_node(self, node_id: str | None) -> list[Any]:
        """Get edges from a node."""
        if not node_id:
            return []
        return self._flow.edges_from.get(node_id, [])

    def _get_edge_description(self, edge: Any) -> str:
        """Get description for an edge."""
        if hasattr(edge, "condition_description"):
            return str(edge.condition_description)
        if hasattr(edge, "label"):
            return str(edge.label)
        target = self._flow.nodes.get(edge.target)
        if target and hasattr(target, "label"):
            return str(target.label)
        return f"Go to {edge.target}"

    def _get_unanswered_questions(self, ctx: FlowContext) -> list[dict[str, Any]]:
        """Get all unanswered question nodes."""
        unanswered = []

        for node_id, node in self._flow.nodes.items():
            if isinstance(node, QuestionNode):
                if node.key not in ctx.answers or ctx.answers[node.key] in (None, ""):
                    unanswered.append(
                        {
                            "id": node.id,
                            "key": node.key,
                            "prompt": node.prompt,
                            "priority": getattr(node, "priority", 100),
                        }
                    )

        return sorted(unanswered, key=lambda x: x["priority"])

    def _suggest_actions(self, node: QuestionNode, ctx: FlowContext) -> list[str]:
        """Suggest possible actions for the current node."""
        suggestions = []

        # Add common suggestions based on node metadata
        if node.meta.get("allows_skip"):
            suggestions.append("skip")
        if node.meta.get("allows_multiple"):
            suggestions.append("add_more")
        if ctx.get_node_state(node.id).visits > 0:
            suggestions.append("change_answer")

        return suggestions

    def _handle_no_node(self, ctx: FlowContext) -> EngineResponse:
        """Handle case when there's no current node."""
        return EngineResponse(
            kind="escalate",
            message="Perdi o contexto de onde estamos. Vou chamar alguém para ajudar.",
            node_id=None,
            metadata={"error": "no_current_node"},
        )

    def _handle_dead_end(self, ctx: FlowContext, node: Any) -> EngineResponse:
        """Handle dead end in the flow."""
        return EngineResponse(
            kind="escalate",
            message="Cheguei a um ponto inesperado. Vou transferir você para alguém que possa ajudar.",
            node_id=node.id,
            metadata={"error": "dead_end"},
        )

    def _generate_decision_prompt(self, node: DecisionNode, options: list[str]) -> str:
        """Generate a decision prompt."""
        if not options:
            return "Qual caminho você gostaria de seguir?"
        if len(options) == 1:
            return f"Vamos seguir por {options[0]}?"
        opt_text = ", ".join(options[:-1]) + f" ou {options[-1]}"
        return f"Qual caminho você prefere: {opt_text}?"
