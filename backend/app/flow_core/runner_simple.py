"""Simplified flow runner using the pure state machine engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

    from .compiler import CompiledFlow

from .constants import TOOL_NAVIGATE_TO_NODE, TOOL_UPDATE_ANSWERS
from .engine_simple import SimpleFlowEngine
from .llm_responder import LLMFlowResponder
from .state import FlowContext

logger = logging.getLogger(__name__)


@dataclass
class SimpleTurnResult:
    """Result of processing a turn in the simplified flow."""

    assistant_message: str | None = None
    messages: list[dict[str, Any]] | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    answers_diff: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_complete: bool = False
    is_escalated: bool = False


class SimpleFlowRunner:
    """
    Simplified flow runner that orchestrates the state machine engine and GPT-5 responder.
    
    Key principles:
    1. Engine provides state and options
    2. GPT-5 makes all decisions via tools
    3. Runner coordinates between them
    """

    def __init__(
        self,
        compiled_flow: CompiledFlow,
        llm_client: LLMClient,
        use_all_tools: bool = True,
    ):
        """Initialize the runner with engine and responder."""
        self._engine = SimpleFlowEngine(compiled_flow)
        self._responder = LLMFlowResponder(llm_client, use_all_tools=use_all_tools)
        self._flow = compiled_flow

    def initialize_context(self, existing_context: FlowContext | None = None) -> FlowContext:
        """Initialize or restore flow context."""
        return self._engine.initialize_context(existing_context)

    def process_turn(
        self,
        ctx: FlowContext,
        user_message: str | None = None,
        project_context: ProjectContext | None = None,
    ) -> SimpleTurnResult:
        """
        Process a turn in the conversation.
        
        This orchestrates:
        1. Getting current state from engine
        2. Having GPT-5 decide on tool and messages
        3. Executing the tool action in the engine
        4. Returning the complete result
        """
        # Track answers before processing
        initial_answers = dict(ctx.answers)

        # Get current state from engine
        engine_state = self._engine.get_state(ctx, user_message)

        # Check for terminal or error states
        if engine_state.state.is_complete:
            return SimpleTurnResult(
                assistant_message=engine_state.prompt or "Conversa concluída!",
                is_complete=True,
                metadata=engine_state.metadata,
            )

        if engine_state.state.error:
            logger.error(f"Engine error: {engine_state.state.error}")
            return SimpleTurnResult(
                assistant_message="Encontrei um problema. Vou chamar alguém para ajudar.",
                is_escalated=True,
                metadata={"error": engine_state.state.error},
            )

        # Prepare available edges for responder
        available_edges = None
        if engine_state.state.available_edges:
            available_edges = [
                {
                    "target_node_id": edge.target_node_id,
                    "description": edge.description or f"Go to {edge.target_node_id}",
                    "condition": edge.condition,
                }
                for edge in engine_state.state.available_edges
            ]

        # Use GPT-5 to decide on tool and generate messages
        responder_result = self._responder.respond(
            prompt=engine_state.prompt or "",
            pending_field=ctx.pending_field,
            ctx=ctx,
            user_message=user_message or "",
            project_context=project_context,
            available_edges=available_edges,
        )

        # Process the tool response
        if responder_result.tool_name == TOOL_NAVIGATE_TO_NODE:
            # Execute navigation in engine
            target_node = responder_result.tool_args.get("target_node_id")
            if target_node:
                new_state = self._engine.navigate_to(ctx, target_node)
                if new_state.state.error:
                    logger.warning(f"Navigation failed: {new_state.state.error}")
                    # Stay on current node if navigation fails
                else:
                    # Successfully navigated
                    logger.info(f"Navigated to node: {target_node}")

        elif responder_result.tool_name == TOOL_UPDATE_ANSWERS:
            # Update answers in engine
            updates = responder_result.updates or {}
            for field, value in updates.items():
                self._engine.update_answer(ctx, field, value)
                logger.info(f"Updated answer: {field} = {value}")

            # Advance from current node after updating
            self._engine.advance_from_current(ctx)

        # Calculate answers diff
        answers_diff = {
            k: v for k, v in ctx.answers.items()
            if k not in initial_answers or initial_answers[k] != v
        }

        # Build result
        return SimpleTurnResult(
            assistant_message=responder_result.assistant_message,
            messages=responder_result.messages,
            tool_name=responder_result.tool_name,
            tool_args=responder_result.tool_args,
            answers_diff=answers_diff,
            metadata={
                **responder_result.metadata,
                "current_node": ctx.current_node_id,
                "pending_field": ctx.pending_field,
            },
            is_complete=ctx.is_complete,
            is_escalated=responder_result.terminal,
        )
