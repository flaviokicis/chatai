"""Channel-agnostic flow processing engine.

This module provides a clean, loosely coupled interface for processing messages
through conversational flows. It follows FAANG-level engineering practices:

- Dependency Injection: All dependencies are injected via interfaces
- Single Responsibility: Only handles flow processing logic
- Open/Closed Principle: Extensible via interfaces without modification
- Liskov Substitution: All implementations are interchangeable
- Interface Segregation: Small, focused interfaces
- Dependency Inversion: Depends on abstractions, not concretions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

from app.core.thought_tracer import DatabaseThoughtTracer
from app.db.session import create_session
from app.flow_core.compiler import compile_flow
from app.flow_core.ir import Flow
from app.flow_core.runner import FlowTurnRunner
from app.services.admin_phone_service import AdminPhoneService
from app.services.processing_cancellation_manager import ProcessingCancellationManager, ProcessingCancelledException

if TYPE_CHECKING:
    from uuid import UUID

    from app.core.llm import LLMClient
    from app.flow_core.state import FlowContext
    from app.services.tenant_config_service import ProjectContext

logger = logging.getLogger(__name__)


class FlowProcessingResult(Enum):
    """Result types for flow processing."""

    CONTINUE = "continue"
    TERMINAL = "terminal"
    ESCALATE = "escalate"
    ERROR = "error"


@dataclass(frozen=True)
class FlowRequest:
    """Immutable request for flow processing."""

    user_id: str
    user_message: str
    flow_definition: dict[str, Any]
    flow_metadata: dict[str, Any]  # flow_name, flow_id, etc.
    tenant_id: UUID  # type: ignore[name-defined]
    project_context: ProjectContext  # type: ignore[name-defined]
    channel_id: str | None = None  # Channel identifier for customer traceability


@dataclass(frozen=True)
class FlowResponse:
    """Immutable response from flow processing."""

    result: FlowProcessingResult
    message: str | None
    context: FlowContext | None  # type: ignore[name-defined]
    metadata: dict[str, Any]
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """Check if processing was successful."""
        return self.result != FlowProcessingResult.ERROR

    @property
    def should_continue(self) -> bool:
        """Check if flow should continue."""
        return self.result == FlowProcessingResult.CONTINUE


class SessionManager(Protocol):
    """Interface for managing flow sessions and context persistence."""

    def create_session(self, user_id: str, flow_id: str) -> str:
        """Create a new flow session."""
        ...

    def load_context(self, session_id: str) -> FlowContext | None:
        """Load existing flow context."""
        ...

    def save_context(self, session_id: str, context: FlowContext) -> None:
        """Save flow context."""
        ...

    def clear_context(self, session_id: str) -> None:
        """Clear flow context."""
        ...



class ThreadStatusUpdater(Protocol):
    """Interface for updating thread status after flow completion."""

    def update_completion_status(
        self,
        thread_id: UUID,
        flow_response: FlowResponse,
        request: FlowRequest,
    ) -> None:
        """Update thread status after flow completion."""
        ...


class FlowProcessingError(Exception):
    """Base exception for flow processing errors."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class FlowProcessor:
    """
    Channel-agnostic flow processing engine.
    
    This class orchestrates flow processing while remaining completely
    independent of any specific communication channel. It uses dependency
    injection to achieve loose coupling with external systems.
    
    Key design principles:
    - No direct dependencies on channel-specific code
    - All external systems accessed via interfaces
    - Immutable request/response objects
    - Comprehensive error handling
    - Thread-safe operations
    """

    def __init__(
        self,
        llm: LLMClient,
        session_manager: SessionManager,
        training_handler: None = None,  # Deprecated, kept for compatibility
        thread_updater: ThreadStatusUpdater | None = None,
    ) -> None:
        """
        Initialize the flow processor.
        
        Args:
            llm: LLM client for flow processing
            session_manager: Session and context management
            training_handler: Deprecated parameter (ignored)
            thread_updater: Optional thread status updater
        """
        self._llm = llm
        self._session_manager = session_manager
        self._thread_updater = thread_updater
        # Pass the session manager's store to cancellation manager for Redis access
        store = getattr(session_manager, '_store', None)
        self._cancellation_manager = ProcessingCancellationManager(store=store)

    def _check_admin_status(self, request: FlowRequest) -> bool:
        """
        Check if the user making the request is an admin.
        
        Args:
            request: The flow request containing user and tenant information
            
        Returns:
            True if user is admin, False otherwise
        """
        try:
            # Extract phone number from user_id (e.g., "whatsapp:+5511999999999")
            user_phone = request.user_id

            # Get tenant ID from project context
            if not request.project_context:
                return False
            tenant_id = request.project_context.tenant_id

            # Check admin status
            with create_session() as session:
                admin_service = AdminPhoneService(session)
                return admin_service.is_admin_phone(user_phone, tenant_id)

        except Exception as e:
            logger.exception(f"Error checking admin status: {e}")
            return False

    async def process_flow(
        self,
        request: FlowRequest,
        app_context: Any,  # TODO: Create proper AppContext interface
    ) -> FlowResponse:
        """
        Process a message through the flow engine.
        
        This is the main entry point that coordinates all flow processing
        while maintaining loose coupling with external systems.
        
        Args:
            request: Immutable flow processing request
            app_context: Application context (temporary - will be abstracted)
            
        Returns:
            Immutable flow processing response
        """
        session_id = None
        try:
            # Step 1: Create session and acquire lock
            session_id = self._session_manager.create_session(
                request.user_id,
                request.flow_metadata.get("flow_id", "unknown")
            )

            performed_aggregation = False

            # Add current message to buffer immediately to ensure cross-request visibility
            if request.user_message:
                self._cancellation_manager.add_message_to_buffer(session_id, request.user_message)
                
                # Wait a very short time to catch truly rapid messages
                # We can't wait too long or we'll delay every single message
                import asyncio
                initial_wait = 0.2  # Wait 200ms to catch rapid succession messages
                logger.debug(f"Waiting {initial_wait}s for potential rapid messages...")
                await asyncio.sleep(initial_wait)

            # Check if we should cancel ongoing processing for rapid messages
            if request.user_message and self._cancellation_manager.should_cancel_processing(session_id):
                logger.info(f"Cancelling ongoing processing for session {session_id} due to new message")
                # Cancel the ongoing processing
                self._cancellation_manager.cancel_processing(session_id)
                
                # Wait for a bit longer to allow:
                # 1. Previous processing to stop
                # 2. More messages to potentially arrive for aggregation
                import asyncio
                wait_time = 1.5  # Increased from 0.5 to allow more messages to arrive
                logger.info(f"Waiting {wait_time}s for message aggregation...")
                await asyncio.sleep(wait_time)
                
                # Get all buffered messages
                aggregated_message = self._cancellation_manager.get_aggregated_messages(session_id)
                if aggregated_message:
                    from dataclasses import replace
                    request = replace(request, user_message=aggregated_message)
                    logger.info(f"Processing aggregated message for session {session_id}: {aggregated_message[:100]}...")
                    performed_aggregation = True
                    # Clear the cancellation flag so the aggregated message can be processed
                    self._cancellation_manager.clear_cancellation_flag(session_id)
                else:
                    # No messages to aggregate, this request was cancelled
                    logger.info(f"No messages to aggregate for cancelled session {session_id}, exiting")
                    self._cancellation_manager.mark_processing_complete(session_id)
                    return FlowResponse(
                        result=FlowProcessingResult.ERROR,
                        message="Processing cancelled - messages being aggregated",
                        context=None,
                        metadata={"cancelled": True}
                    )

            # Add current message to buffer for future aggregation ONLY if we did not already
            # aggregate and replace the request.user_message above. If aggregated, the buffer
            # has been consumed; re-adding would duplicate content.
            # If aggregation did not occur, the single message is already buffered above

            try:
                # Create cancellation token for this processing
                cancellation_token = self._cancellation_manager.create_cancellation_token(session_id)
                
                # Step 2: Process through flow engine with cancellation support
                flow_response = await self._execute_flow(
                    request, session_id, app_context, cancellation_token
                )

                # Step 3: Update thread status if needed
                if (self._thread_updater and
                    flow_response.result in [FlowProcessingResult.TERMINAL, FlowProcessingResult.ESCALATE]):

                    thread_id = request.flow_metadata.get("thread_id")
                    if thread_id:
                        self._thread_updater.update_completion_status(
                            thread_id, flow_response, request
                        )

                # Step 5: Persist context
                if flow_response.should_continue and flow_response.context:
                    self._session_manager.save_context(session_id, flow_response.context)
                elif flow_response.result == FlowProcessingResult.TERMINAL:
                    self._session_manager.clear_context(session_id)

                # Add session_id to metadata for downstream cancellation checks
                if not flow_response.metadata:
                    flow_response.metadata = {}
                flow_response.metadata["session_id"] = session_id
                flow_response.metadata["cancellation_manager"] = self._cancellation_manager
                
                # DO NOT mark processing complete here - let the message_processor do it
                # after the message is actually sent. This keeps the cancellation window open.
                
                return flow_response

            finally:
                # Only clear on error/exception, not on success
                pass

        except Exception as e:
            logger.exception("Flow processing failed for user %s", request.user_id)
            # Clear processing state on error
            if session_id:
                self._cancellation_manager.mark_processing_complete(session_id)
            return FlowResponse(
                result=FlowProcessingResult.ERROR,
                message=None,
                context=None,
                metadata={},
                error=str(e),
            )

    async def _execute_flow(
        self,
        request: FlowRequest,
        session_id: str,
        app_context: Any,
        cancellation_token: Any = None,
    ) -> FlowResponse:
        """Execute the flow with the engine."""
        try:
            # Check for empty flow before compilation
            flow_def = request.flow_definition
            is_empty_flow = (
                not flow_def.get("nodes") or
                not flow_def.get("entry") or
                flow_def.get("entry") == "" or
                len(flow_def.get("nodes", [])) == 0
            )

            if is_empty_flow:
                logger.info("Detected empty flow, showing flow building message")
                return FlowResponse(
                    result=FlowProcessingResult.CONTINUE,
                    message="Ola! O fluxo está vazio. Vamos começar a construir juntos! Como você gostaria que eu cumprimente seus clientes?",
                    context=None,
                    metadata={"empty_flow": True, "flow_building_mode": True},
                )

            # Compile flow
            flow = Flow.model_validate(request.flow_definition)
            compiled_flow = compile_flow(flow)

            # Load existing context
            existing_context = self._session_manager.load_context(session_id)
            
            # Debug: Log what's in the loaded context
            if existing_context and existing_context.history:
                logger.debug(f"Loaded context has {len(existing_context.history)} history turns:")
                for i, turn in enumerate(existing_context.history[-5:]):  # Last 5 turns
                    logger.debug(f"  Turn {i}: {turn.role} - {turn.content[:50]}...")
            else:
                logger.debug("No history in loaded context")

            # Execute with thought tracing
            with create_session() as thought_session:
                thought_tracer = DatabaseThoughtTracer(thought_session)

                # Check if user is admin for live flow modification
                extra_tools = []
                instruction_prefix = ""

                # Check admin status
                is_admin = self._check_admin_status(request)
                if is_admin:
                    from app.flow_core.tool_schemas import ModifyFlowLive
                    extra_tools.append(ModifyFlowLive)
                    instruction_prefix = (
                        "ADMIN MODE: You have access to live flow modification.\n"
                        "Use ModifyFlowLive ONLY when the user gives clear instructions about changing flow behavior.\n"
                        "Examples: 'você deveria perguntar sobre tipo de unha', 'next time ask about X first'\n"
                        "Do NOT use this tool for regular conversation or questions about the flow.\n"
                    )

                # Track modification outcome for ModifyFlowLive and provide explicit user feedback
                modification_intercepted = False
                modification_message: str | None = None
                modification_was_applied: bool = False

                # Check for cancellation before processing
                try:
                    self._cancellation_manager.check_cancellation_and_raise(session_id, "flow_processing")
                except ProcessingCancelledException:
                    logger.info(f"Processing cancelled for session {session_id}")
                    # Mark as complete to clean up state
                    self._cancellation_manager.mark_processing_complete(session_id)
                    return FlowResponse(
                        result=FlowProcessingResult.ERROR,
                        message="Processing cancelled - new message received",
                        context=existing_context,
                        metadata={"cancelled": True}
                    )

                # Create tool event handler for live flow modification and restart
                def on_tool_event(tool_name: str, metadata: dict[str, Any]) -> bool:
                    if tool_name == "ModifyFlowLive":
                        print(f"[DEBUG PROCESSOR] ModifyFlowLive requested by user: {request.user_id}")
                        print(f"[DEBUG PROCESSOR] User is admin: {is_admin}")

                        if not is_admin:
                            logger.warning(f"Non-admin user {request.user_id} attempted flow modification")
                            return False  # Don't intercept - let normal flow handle it

                        # Handle live flow modification
                        instruction = metadata.get("instruction", "")
                        print(f"[DEBUG PROCESSOR] Admin instruction: {instruction}")
                        if instruction:
                            try:
                                import asyncio
                                from uuid import UUID

                                # Handle both string and UUID types
                                flow_id_raw = request.flow_metadata.get("selected_flow_id", "")
                                if isinstance(flow_id_raw, UUID):
                                    flow_id = flow_id_raw
                                else:
                                    flow_id = UUID(flow_id_raw)

                                # Use the existing FlowChatService in a thread pool to avoid event loop conflicts
                                import concurrent.futures

                                from app.agents.flow_chat_agent import FlowChatAgent, ToolSpec
                                from app.agents.flow_modification_tools import (
                                    FLOW_MODIFICATION_TOOLS,
                                )
                                from app.services.flow_chat_service import (
                                    FlowChatService,
                                    FlowChatServiceResponse,
                                )

                                def run_flow_chat_modification() -> FlowChatServiceResponse:
                                    """Run the flow modification using the existing FlowChatService in a separate thread."""
                                    # Create a new event loop for this thread
                                    new_loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(new_loop)
                                    try:
                                        # Build the same agent the frontend uses
                                        tools = []
                                        for tool_config in FLOW_MODIFICATION_TOOLS:
                                            tools.append(ToolSpec(
                                                name=tool_config["name"],
                                                description=tool_config["description"],
                                                args_schema=tool_config["args_schema"],
                                                func=tool_config["func"]
                                            ))
                                        agent = FlowChatAgent(llm=self._llm, tools=tools)

                                        with create_session() as mod_session:
                                            service = FlowChatService(mod_session, agent=agent)

                                            # Enhance the instruction with flow safety guidelines
                                            enhanced_instruction = f"""
{instruction}

CRITICAL FLOW SAFETY RULES:
1. NEVER delete nodes that break user flow paths - always preserve connectivity
2. When removing/skipping a question, redirect edges to maintain flow continuity
3. If deleting node X that connects A→X→B, ensure A connects to B directly
4. Before any deletion, check if it breaks decision paths (e.g., "campo de futebol" route)
5. When user says "remove question", they mean "skip it" not "break the flow path"
6. ALWAYS validate flow connectivity after modifications
"""

                                            # Run the async operation in this thread's event loop
                                            return new_loop.run_until_complete(
                                                service.send_user_message(flow_id, enhanced_instruction)
                                            )
                                    finally:
                                        new_loop.close()

                                # Run in thread pool with timeout and wait for completion
                                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                                    future = executor.submit(run_flow_chat_modification)
                                    try:
                                        result = future.result(timeout=180.0)  # 3 minute timeout for complex modifications

                                        # Determine success message based on actual results
                                        if result.flow_was_modified:
                                            success_msg = "✅ Modificação aplicada com sucesso! As alterações já estão ativas no fluxo."
                                            if result.modification_summary:
                                                success_msg += f"\n\nResumo: {result.modification_summary}"
                                            success_msg += "\n\n🔄 O fluxo foi reiniciado. A conversa agora começa do início para que você possa testar as mudanças."

                                            # Clear session context to restart conversation
                                            try:
                                                self._session_manager.clear_context(session_id)
                                                logger.info(f"Cleared session context for {session_id} after flow modification")
                                            except Exception as e:
                                                logger.warning(f"Failed to clear session context after flow modification: {e}")

                                            modification_was_applied = True
                                            modification_message = success_msg
                                            modification_intercepted = True
                                        else:
                                            info_msg = "ℹ️ Instrução processada, mas nenhuma modificação foi necessária no fluxo."
                                            modification_was_applied = False
                                            modification_message = info_msg
                                            modification_intercepted = True

                                        logger.info(
                                            "Live flow modification completed via FlowChatService: modified=%s",
                                            result.flow_was_modified,
                                        )
                                        logger.info("Returning message to user: %s", modification_message)
                                        print(
                                            f"[DEBUG PROCESSOR] Flow chat modification completed: {result.flow_was_modified}"
                                        )

                                        return True
                                        
                                    except concurrent.futures.TimeoutError:
                                        logger.error("Live flow modification timed out")
                                        print("[DEBUG PROCESSOR] Modification timed out")
                                        modification_was_applied = False
                                        modification_message = "❌ Modificação expirou. Tente novamente com uma instrução mais simples."
                                        modification_intercepted = True
                                        return True
                            except Exception as e:
                                logger.exception(f"Live flow modification failed: {e}")
                                print(f"[DEBUG PROCESSOR] Modification failed: {e}")
                                # Log specific error for admin feedback
                                logger.error(f"Live flow modification failed for admin {request.user_id}: {e}")
                                modification_was_applied = False
                                modification_message = f"❌ Falha ao modificar o fluxo: {e!s}"
                                modification_intercepted = True
                                return True

                        # Intercepted; skip normal flow and respond with explicit message
                        modification_intercepted = True
                        return True

                    return False

                # Create and run flow
                runner = FlowTurnRunner(
                    compiled_flow=compiled_flow,
                    llm=self._llm,
                    strict_mode=True,
                    thought_tracer=thought_tracer,
                    extra_tools=extra_tools,
                    instruction_prefix=instruction_prefix,
                    on_tool_event=on_tool_event,
                )

                # Initialize context
                ctx = runner.initialize_context(existing_context)
                ctx.user_id = request.user_id
                ctx.session_id = session_id
                ctx.tenant_id = request.tenant_id
                ctx.channel_id = request.channel_id

                # Process the turn
                result = runner.process_turn(
                    ctx=ctx,
                    user_message=request.user_message,
                    project_context=request.project_context
                )



                # If we intercepted ModifyFlowLive, return the explicit success/error message
                if 'modification_intercepted' in locals() and modification_intercepted:
                    return FlowResponse(
                        result=FlowProcessingResult.CONTINUE,
                        message=modification_message or "",
                        context=result.ctx,
                        metadata={
                            "tool_name": "ModifyFlowLive",
                            "flow_modified": modification_was_applied,
                        },
                    )



                # Handle AutoReset from escalation - clear session context
                if result.tool_name == "AutoReset":
                    try:
                        self._session_manager.clear_context(session_id)
                        logger.info(f"Cleared session context after auto-reset for {session_id}")
                    except Exception as e:
                        logger.warning(f"Failed to clear session context after auto-reset: {e}")

                # Map result to response
                if result.escalate:
                    flow_result = FlowProcessingResult.ESCALATE
                elif result.terminal:
                    flow_result = FlowProcessingResult.TERMINAL
                else:
                    flow_result = FlowProcessingResult.CONTINUE

                # Build metadata including all tool metadata
                response_metadata = {
                    "tool_name": result.tool_name,
                    "answers_diff": result.answers_diff,
                }
                
                # Include all metadata from the turn result (including ack_message)
                if result.metadata:
                    response_metadata.update(result.metadata)
                
                return FlowResponse(
                    result=flow_result,
                    message=result.assistant_message,
                    context=result.ctx,
                    metadata=response_metadata,
                )

        except Exception as e:
            error_msg = f"Flow execution failed: {e!s}"
            raise FlowProcessingError(error_msg, e) from e
