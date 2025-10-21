"""Enhanced LLM-based responder using GPT-5 for both tool calling and message generation.

This module provides a clean interface to the enhanced responder service that combines
tool calling and natural message generation in a single cohesive step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.llm import LLMClient

    # Thought tracing removed - using Langfuse for observability
    from app.services.tenant_config_service import ProjectContext

    from .state import FlowContext

from app.core.flow_response import FlowProcessingResult
from app.core.flow_response import FlowResponse as UnifiedFlowResponse

from .services.responder import EnhancedFlowResponder


@dataclass(slots=True)
class ResponseConfig:
    """Configuration for LLM response generation."""

    allowed_values: list[str] | None = None
    agent_custom_instructions: str | None = None
    project_context: ProjectContext | None = None
    is_completion: bool = False
    available_edges: list[dict[str, Any]] | None = None
    is_admin: bool = False
    flow_graph: dict[str, Any] | None = None


# No local FlowResponse dataclass - use the unified one from app.core.flow_response


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
        llm: LLMClient,
    ) -> None:
        """
        Initialize the responder.

        Args:
            llm: The LLM client (GPT-5) for processing
        """
        self._enhanced_responder = EnhancedFlowResponder(llm)

    async def respond(
        self,
        prompt: str,
        pending_field: str | None,
        ctx: FlowContext,
        user_message: str,
        config: ResponseConfig | None = None,
    ) -> UnifiedFlowResponse:
        """
        Generate a response using enhanced GPT-5 processing.

        Args:
            prompt: The current question prompt
            pending_field: The field we're trying to fill
            ctx: The flow context with history and state
            user_message: The user's message
            config: Optional configuration for response generation

        Returns:
            FlowResponse with updates, messages, and metadata
        """
        # Use default config if none provided
        if config is None:
            config = ResponseConfig()

        # Determine if this is a completion
        is_completion = ctx.is_complete or config.is_completion

        # Merge custom instructions into prompt if provided
        enhanced_prompt = prompt
        if config.agent_custom_instructions:
            enhanced_prompt = f"{config.agent_custom_instructions}\n\n{prompt}"

        # Call the enhanced responder
        output = await self._enhanced_responder.respond(
            prompt=enhanced_prompt,
            pending_field=pending_field,
            context=ctx,
            user_message=user_message,
            allowed_values=config.allowed_values,
            project_context=config.project_context,
            is_completion=is_completion,
            available_edges=config.available_edges,
            is_admin=config.is_admin,
            flow_graph=config.flow_graph,
        )

        # Convert to FlowResponse format
        result = output.tool_result

        # Use first message as primary message
        primary_message = output.messages[0]["text"] if output.messages else ""

        # Build metadata with messages for downstream channel adapter
        metadata = dict(result.metadata or {})
        if output.messages:
            metadata["messages"] = [dict(msg) for msg in output.messages]

        return UnifiedFlowResponse(
            result=FlowProcessingResult.CONTINUE
            if not result.terminal and not result.escalate
            else (
                FlowProcessingResult.ESCALATE if result.escalate else FlowProcessingResult.TERMINAL
            ),
            message=primary_message,
            context=ctx,
            metadata=metadata,
        )
