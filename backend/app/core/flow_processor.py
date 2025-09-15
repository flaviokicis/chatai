"""Clean flow processor with external action feedback support.

This processor uses the new clean architecture that ensures external actions
are properly executed and their results are fed back to the LLM.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from app.core.llm import LLMClient
from app.core.session import SessionManager
from app.flow_core.compiler import FlowCompiler
from app.flow_core.runner import FlowTurnRunner
from app.services.processing_cancellation_manager import ProcessingCancellationManager

from .flow_request import FlowRequest
from .flow_response import FlowProcessingResult, FlowResponse

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)


class ThreadStatusUpdater(ABC):
    """Abstract base class for thread status updating strategies."""

    @abstractmethod
    def update_completion_status(
        self,
        thread_id: UUID,
        flow_response: FlowResponse,
        request: FlowRequest,
    ) -> None:
        """Update thread status after flow completion.

        Args:
            thread_id: The thread identifier
            flow_response: The flow processing response
            request: The original flow request
        """


class FlowProcessor:
    """Flow processor with external action feedback loops.

    This processor ensures that all external actions are properly
    executed with LLM feedback.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        session_manager: SessionManager,
        cancellation_manager: ProcessingCancellationManager,
    ):
        """Initialize the flow processor.

        Args:
            llm_client: LLM client for generating responses
            session_manager: Session management
            cancellation_manager: Processing cancellation management
        """
        self._llm = llm_client
        self._session_manager = session_manager
        self._cancellation_manager = cancellation_manager

        # Create action registry once and reuse it
        from app.flow_core.actions import ActionRegistry

        self._action_registry = ActionRegistry(llm_client)

        logger.info("FlowProcessor initialized")

    async def process_flow(self, request: FlowRequest, app_context: Any) -> FlowResponse:
        """Process a flow request with external action handling.

        Args:
            request: Flow processing request
            app_context: Application context

        Returns:
            Flow response with truthful action results
        """
        session_id = self._build_session_id(request)

        logger.info("=" * 80)
        logger.info("🎯 FLOW PROCESSOR: Processing request")
        logger.info("=" * 80)
        logger.info(f"User: {request.user_id}")
        logger.info(f"Session: {session_id}")
        logger.info(
            f"Message: {request.user_message[:100]}..."
            if len(request.user_message) > 100
            else f"Message: {request.user_message}"
        )
        logger.info("=" * 80)

        # Initialize existing_context early to avoid UnboundLocalError
        existing_context = None

        try:
            # Check for cancellation
            self._cancellation_manager.check_cancellation_and_raise(session_id, "flow_processing")

            # Get or create flow context
            existing_context = self._session_manager.get_context(session_id)

            # Compile flow (prefer typed field; support legacy metadata fallback)
            flow_definition = request.flow_definition or request.flow_metadata.get(
                "flow_definition", {}
            )
            if not flow_definition:
                raise ValueError("No flow definition provided")

            # Convert dict to Flow object if needed
            from app.flow_core.ir import Flow

            if isinstance(flow_definition, dict):
                flow_obj = Flow.model_validate(flow_definition)
            else:
                flow_obj = flow_definition

            compiler = FlowCompiler()
            compiled_flow = compiler.compile(flow_obj)

            # Check admin status
            is_admin = self._check_admin_status(request)

            # Create runner with shared action registry
            runner = FlowTurnRunner(self._llm, compiled_flow, self._action_registry)

            # Initialize context
            ctx = runner.initialize_context(existing_context)
            ctx.user_id = request.user_id
            ctx.session_id = session_id
            ctx.tenant_id = request.tenant_id
            ctx.channel_id = request.channel_id

            # Validate flow metadata and get flow_id with runtime safety
            from app.core.types import validate_flow_metadata

            try:
                validated_metadata = validate_flow_metadata(request.flow_metadata)
                ctx.flow_id = validated_metadata["selected_flow_id"]
            except ValueError as e:
                logger.warning(f"Flow metadata validation failed: {e}, using fallback")
                ctx.flow_id = request.flow_metadata.get("selected_flow_id", "")

            # Add user message to conversation history
            ctx.add_turn(
                role="user",
                content=request.user_message,
                node_id=ctx.current_node_id,
            )

            # Process the turn
            result = await runner.process_turn(
                ctx=ctx,
                user_message=request.user_message,
                project_context=request.project_context,
                is_admin=is_admin,
            )

            # Add assistant response to conversation history
            messages = result.metadata.get("messages", [])
            if messages:
                # Combine all message texts for history
                response_text = " ".join(
                    msg.get("text", "")
                    for msg in messages
                    if isinstance(msg, dict) and msg.get("text")
                )
                if response_text:
                    ctx.add_turn(
                        role="assistant",
                        content=response_text,
                        node_id=ctx.current_node_id,
                        metadata={"tool": result.metadata.get("tool_name")},
                    )

            # Save updated context with conversation history
            self._session_manager.save_context(session_id, ctx)

            # Build response based on actual results
            return self._build_response(result, ctx)

        except Exception as e:
            logger.error("❌ Flow processing failed", exc_info=True)
            return FlowResponse(
                result=FlowProcessingResult.ERROR,
                message="❌ Erro interno do sistema. Tente novamente.",
                context=existing_context,
                metadata={"error": str(e)},
            )

    def _build_session_id(self, request: FlowRequest) -> str:
        """Build session ID from request."""
        flow_id = request.flow_metadata.get("selected_flow_id", "default")
        return f"flow:{request.user_id}:{flow_id}"

    def _check_admin_status(self, request: FlowRequest) -> bool:
        """Check if the user has admin privileges.

        Args:
            request: Flow request

        Returns:
            True if user is admin, False otherwise
        """
        # For now, all users are considered admin for flow modification
        # This should be replaced with proper admin checking logic
        return True

    def _build_response(self, turn_result: Any, ctx: Any) -> FlowResponse:
        """Build flow response from turn result.

        Args:
            turn_result: Result from the turn runner
            ctx: Flow context

        Returns:
            Flow response
        """
        # Determine result type
        if turn_result.escalate:
            result_type = FlowProcessingResult.ESCALATE
        elif turn_result.terminal:
            result_type = FlowProcessingResult.TERMINAL
        else:
            result_type = FlowProcessingResult.CONTINUE

        # Build metadata
        metadata = turn_result.metadata.copy()

        # Add external action information
        if turn_result.external_action_executed:
            metadata.update(
                {
                    "external_action_executed": True,
                    "external_action_successful": bool(
                        turn_result.external_action_result
                        and turn_result.external_action_result.success
                    ),
                    "tool_name": metadata.get("tool_name", "unknown"),
                }
            )

        # Add messages for responses (from metadata) - include even single messages
        messages = turn_result.metadata.get("messages", [])
        if messages:
            metadata["messages"] = messages

        # Log response details
        logger.info("=" * 80)
        logger.info("📤 BUILDING FLOW RESPONSE")
        logger.info("=" * 80)
        # Get assistant message from metadata or messages
        assistant_message = None
        if messages and len(messages) > 0:
            # Get the first message content/text
            first_msg = messages[0]
            if isinstance(first_msg, dict):
                # Messages can have either 'text' or 'content' field
                assistant_message = first_msg.get("text") or first_msg.get("content", "")
            else:
                assistant_message = str(first_msg)
        else:
            # Fallback to any message in metadata
            assistant_message = metadata.get("message", "")

        logger.info(f"Result type: {result_type}")
        logger.info(f"Message: {assistant_message}")
        logger.info(f"External action executed: {turn_result.external_action_executed}")
        logger.info(
            f"External action successful: {bool(turn_result.external_action_result and turn_result.external_action_result.success)}"
        )
        logger.info("=" * 80)

        return FlowResponse(
            result=result_type,
            message=assistant_message or "",
            context=ctx,
            metadata=metadata,
        )
