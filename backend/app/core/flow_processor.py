"""Clean flow processor with external action feedback support.

This processor uses the new clean architecture that ensures external actions
are properly executed and their results are fed back to the LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.llm import LLMClient
from app.core.session import SessionManager
from app.flow_core.compiler import FlowCompiler
from app.flow_core.runner import FlowTurnRunner
from app.services.processing_cancellation_manager import ProcessingCancellationManager

from .flow_request import FlowRequest
from .flow_response import FlowProcessingResult, FlowResponse

logger = logging.getLogger(__name__)


class FlowProcessor:
    """Clean flow processor with external action feedback loops.
    
    This processor eliminates the complex interception logic and ensures
    that all external actions are properly executed with LLM feedback.
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
        
        logger.info("FlowProcessor initialized with clean architecture")

    async def process_flow(self, request: FlowRequest, app_context: Any) -> FlowResponse:
        """Process a flow request with clean external action handling.
        
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
        logger.info(f"Message: {request.user_message[:100]}..." if len(request.user_message) > 100 else f"Message: {request.user_message}")
        logger.info("=" * 80)

        try:
            # Check for cancellation
            self._cancellation_manager.check_cancellation_and_raise(session_id, "flow_processing")

            # Get or create flow context
            existing_context = self._session_manager.get_context(session_id)

            # Compile flow
            flow_definition = request.flow_metadata.get("flow_definition", {})
            if not flow_definition:
                raise ValueError("No flow definition provided")
            
            compiler = FlowCompiler()
            compiled_flow = compiler.compile(flow_definition)

                # Check admin status
                is_admin = self._check_admin_status(request)

            # Create clean runner
            runner = FlowTurnRunner(self._llm, compiled_flow)

                # Initialize context
                ctx = runner.initialize_context(existing_context)
                ctx.user_id = request.user_id
                ctx.session_id = session_id
                ctx.tenant_id = request.tenant_id
                ctx.channel_id = request.channel_id
            ctx.flow_id = request.flow_metadata.get("selected_flow_id", "")

            # Process the turn with clean architecture
            result = await runner.process_turn(
                    ctx=ctx,
                    user_message=request.user_message,
                    project_context=request.project_context,
                    is_admin=is_admin
                )

            # Save updated context
            self._session_manager.save_context(session_id, ctx)

            # Build response based on actual results
            return self._build_response(result, ctx)

        except Exception as e:
            logger.error("❌ Flow processing failed", exc_info=True)
            return FlowResponse(
                result=FlowProcessingResult.ERROR,
                message="❌ Erro interno do sistema. Tente novamente.",
                context=existing_context,
                metadata={"error": str(e)}
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
            metadata.update({
                "external_action_executed": True,
                "external_action_successful": turn_result.external_action_successful,
                "tool_name": turn_result.tool_name,
            })

        # Add messages for multi-message responses
        if turn_result.messages and len(turn_result.messages) > 1:
            metadata["messages"] = turn_result.messages

        # Log response details
        logger.info("=" * 80)
        logger.info("📤 BUILDING FLOW RESPONSE")
        logger.info("=" * 80)
        logger.info(f"Result type: {result_type}")
        logger.info(f"Message: {turn_result.assistant_message}")
        logger.info(f"External action executed: {turn_result.external_action_executed}")
        logger.info(f"External action successful: {turn_result.external_action_successful}")
        logger.info("=" * 80)

        return FlowResponse(
            result=result_type,
            message=turn_result.assistant_message or "",
            context=ctx,
            metadata=metadata
            )
