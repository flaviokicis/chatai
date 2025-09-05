"""Enhanced LLM-based responder using GPT-5 for both tool calling and message generation.

This module provides a clean interface to the enhanced responder service that combines
tool calling and natural message generation in a single cohesive step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.core.thought_tracer import DatabaseThoughtTracer
    from app.services.tenant_config_service import ProjectContext

    from .state import FlowContext

from .services.responder import EnhancedFlowResponder


@dataclass(slots=True)
class FlowResponse:
    """Response from the LLM responder."""

    updates: dict[str, Any]
    message: str  # Primary message (first bubble)
    messages: list[dict[str, Any]] | None = None  # Full WhatsApp-style messages
    tool_name: str | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] | None = None
    escalate: bool = False
    escalate_reason: str | None = None
    navigation: str | None = None  # next node to navigate to


class LLMFlowResponder:
    """
    Enhanced LLM-based responder that combines tool calling with natural message generation.

    This responder uses GPT-5 to:
    - Extract and validate answers
    - Handle clarifications naturally
    - Generate conversational WhatsApp messages
    - Navigate flow intelligently
    - Provide warm, human-like responses
    """

    def __init__(
        self,
        llm: LLMClient,  # type: ignore[name-defined]
        thought_tracer: DatabaseThoughtTracer | None = None,  # type: ignore[name-defined]
    ) -> None:
        """
        Initialize the responder.

        Args:
            llm: The LLM client (GPT-5) for processing
            thought_tracer: Optional thought tracer for debugging
        """
        self._enhanced_responder = EnhancedFlowResponder(llm, thought_tracer)

    def respond(
        self,
        prompt: str,
        pending_field: str | None,
        ctx: FlowContext,  # type: ignore[name-defined]
        user_message: str,
        allowed_values: list[str] | None = None,
        *,
        agent_custom_instructions: str | None = None,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    ) -> FlowResponse:
        """
        Generate a response using enhanced GPT-5 processing.

        Args:
            prompt: The current question prompt
            pending_field: The field we're trying to fill
            ctx: The flow context with history and state
            user_message: The user's message
            allowed_values: Optional list of allowed values for validation
            agent_custom_instructions: Custom instructions (integrated into prompt)
            project_context: Project context for styling

        Returns:
            FlowResponse with updates, messages, and metadata
        """
        # Determine if this is a completion
        is_completion = ctx.is_complete

        # Merge custom instructions into prompt if provided
        enhanced_prompt = prompt
        if agent_custom_instructions:
            enhanced_prompt = f"{agent_custom_instructions}\n\n{prompt}"

        # Call the enhanced responder
        output = self._enhanced_responder.respond(
            prompt=enhanced_prompt,
            pending_field=pending_field,
            context=ctx,
            user_message=user_message,
            allowed_values=allowed_values,
            project_context=project_context,
            is_completion=is_completion,
        )

        # Convert to FlowResponse format
        result = output.tool_result

        # Use first message as primary message
        primary_message = output.messages[0]["text"] if output.messages else ""

        return FlowResponse(
            updates=result.updates,
            message=primary_message,
            messages=output.messages,
            tool_name=output.tool_name,
            confidence=output.confidence,
            metadata=result.metadata,
            escalate=result.escalate,
            escalate_reason=result.metadata.get("reason") if result.escalate else None,
            navigation=result.navigation,
        )
