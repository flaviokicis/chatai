"""Simplified flow runner using the pure state machine engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

    from .compiler import CompiledFlow

from .constants import (
    TOOL_CONFIRM_COMPLETION,
    TOOL_NAVIGATE_TO_NODE,
    TOOL_REQUEST_HANDOFF,
    TOOL_RESTART_CONVERSATION,
    TOOL_STAY_ON_NODE,
    TOOL_UPDATE_ANSWERS,
)
from .engine import LLMFlowEngine
from .llm_responder import FlowResponse, LLMFlowResponder, ResponseConfig
from .state import FlowContext

logger = logging.getLogger(__name__)


@dataclass
class TurnResult:
    """Result of processing a turn in the flow."""

    assistant_message: str | None = None
    messages: list[dict[str, Any]] | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    answers_diff: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    terminal: bool = False
    escalate: bool = False
    confidence: float = 1.0
    reasoning: str | None = None


class FlowTurnRunner:
    """
    Simplified flow runner that orchestrates the state machine engine and GPT-5 responder.
    
    Key principles:
    1. Engine provides state (no LLM decisions)
    2. GPT-5 makes all routing decisions
    3. Runner coordinates between them
    """

    def __init__(
        self,
        compiled_flow: CompiledFlow,
        llm_client: LLMClient,
        use_all_tools: bool = True,
    ):
        """Initialize the runner with engine and responder."""
        self._engine = LLMFlowEngine(compiled_flow, llm_client)
        self._responder = LLMFlowResponder(llm_client)
        self._flow = compiled_flow

    def initialize_context(self, existing_context: FlowContext | None = None) -> FlowContext:
        """Initialize or restore flow context."""
        return self._engine.initialize_context(existing_context)

    def process_turn(
        self,
        ctx: FlowContext,
        user_message: str | None = None,
        project_context: ProjectContext | None = None,
    ) -> TurnResult:
        """
        Process a turn in the conversation.
        
        This orchestrates:
        1. Getting current state from engine
        2. Having GPT-5 decide on tool and messages
        3. Processing the tool action
        4. Returning the result
        """
        # Track answers before processing
        initial_answers = dict(ctx.answers)

        # Get engine response (current state)
        engine_response = self._engine.process(ctx, user_message, project_context=project_context)

        # Handle terminal states
        if engine_response.kind == "terminal":
            return TurnResult(
                assistant_message=engine_response.message,
                terminal=True,
                metadata=engine_response.metadata or {},
            )

        # Handle escalation
        if engine_response.kind == "escalate":
            # Auto-reset on escalation
            print("[DEBUG RUNNER] Engine escalated, marking for session reset")

            return TurnResult(
                assistant_message="Vamos recomeçar! Como posso te ajudar hoje?",
                escalate=True,
                metadata=engine_response.metadata or {},
            )

        # Extract available edges from metadata
        available_edges = None
        if engine_response.metadata and "available_edges" in engine_response.metadata:
            available_edges = engine_response.metadata["available_edges"]

        # Get allowed values if any
        allowed_values = None
        if engine_response.metadata and "allowed_values" in engine_response.metadata:
            allowed_values = engine_response.metadata["allowed_values"]

        # Create response config with additional parameters
        config = ResponseConfig(
            allowed_values=allowed_values,
            project_context=project_context,
            is_completion=False,
            available_edges=available_edges,
        ) if any([allowed_values, project_context, available_edges]) else None

        # Use GPT-5 responder to process
        responder_result = self._responder.respond(
            prompt=engine_response.message or "",
            pending_field=ctx.pending_field,
            ctx=ctx,
            user_message=user_message or "",
            config=config,
        )

        # Convert responder result to engine event and process
        engine_event = self._build_engine_event(responder_result)

        # Special handling for certain tools
        if responder_result.tool_name == TOOL_NAVIGATE_TO_NODE:
            # Navigate to the target node
            if responder_result.navigation:
                engine_event["target_node_id"] = responder_result.navigation

        elif responder_result.tool_name == TOOL_UPDATE_ANSWERS:
            # Update answers and advance
            if responder_result.updates:
                for field, value in responder_result.updates.items():
                    ctx.answers[field] = value
                    # Mark as answer event for engine
                    if field == ctx.pending_field:
                        engine_event["answer"] = value

        elif responder_result.tool_name == TOOL_STAY_ON_NODE:
            # Stay on current node - no navigation
            pass

        elif responder_result.tool_name == TOOL_REQUEST_HANDOFF:
            # Escalate to human
            engine_event["tool_name"] = "RequestHumanHandoff"
            engine_event["reason"] = responder_result.escalate_reason or "requested"

        elif responder_result.tool_name == TOOL_RESTART_CONVERSATION:
            # Restart the conversation
            engine_event["tool_name"] = "RestartConversation"

        elif responder_result.tool_name == TOOL_CONFIRM_COMPLETION:
            # Mark as complete
            ctx.is_complete = True

        # Process the event if needed
        if engine_event and (engine_event.get("target_node_id") or
                            engine_event.get("answer") or
                            engine_event.get("tool_name")):
            final_response = self._engine.process(ctx, None, engine_event)

            # Update metadata with final response info
            if final_response.metadata and responder_result.metadata:
                responder_result.metadata.update(final_response.metadata)

        # Calculate answers diff
        answers_diff = {
            k: v for k, v in ctx.answers.items()
            if k not in initial_answers or initial_answers[k] != v
        }

        # Build final result
        return TurnResult(
            assistant_message=responder_result.message,
            messages=responder_result.messages,
            tool_name=responder_result.tool_name,
            tool_args={"navigation": responder_result.navigation} if responder_result.navigation else None,
            answers_diff=answers_diff,
            metadata=responder_result.metadata or {},
            terminal=ctx.is_complete,
            escalate=responder_result.escalate,
            confidence=responder_result.confidence,
            reasoning=None,  # Not available in FlowResponse
        )

    def _build_engine_event(self, responder_result: FlowResponse) -> dict[str, Any]:
        """Build an engine event from responder result."""
        event: dict[str, Any] = {
            "tool_name": responder_result.tool_name,
        }

        if responder_result.updates:
            event["updates"] = responder_result.updates

        if responder_result.navigation:
            event["navigation"] = responder_result.navigation

        return event
