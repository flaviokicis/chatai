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

    def acquire_lock(self, session_id: str) -> bool:
        """Acquire distributed lock for session."""
        ...

    def release_lock(self, session_id: str) -> None:
        """Release distributed lock for session."""
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

            lock_acquired = self._session_manager.acquire_lock(session_id)
            if not lock_acquired:
                logger.warning("Failed to acquire lock for session %s", session_id)

            try:
                # Step 2: Process through flow engine
                flow_response = await self._execute_flow(request, session_id, app_context)

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

                return flow_response

            finally:
                if lock_acquired:
                    self._session_manager.release_lock(session_id)

        except Exception as e:
            logger.exception("Flow processing failed for user %s", request.user_id)
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
    ) -> FlowResponse:
        """Execute the flow with the engine."""
        try:
            # Compile flow
            flow = Flow.model_validate(request.flow_definition)
            compiled_flow = compile_flow(flow)

            # Load existing context
            existing_context = self._session_manager.load_context(session_id)

            # Execute with thought tracing
            with create_session() as thought_session:
                thought_tracer = DatabaseThoughtTracer(thought_session)

                # Check if user is admin for live flow modification
                extra_tools = []
                instruction_prefix = ""
                
                # Check admin status
                is_admin = self._check_admin_status(request)
                if is_admin:
                    from app.flow_core.tool_schemas import ModifyFlowLive  # noqa: F401
                    extra_tools.append(ModifyFlowLive)
                    instruction_prefix = (
                        "ADMIN MODE: You have access to live flow modification.\n"
                        "Use ModifyFlowLive ONLY when the user gives clear instructions about changing flow behavior.\n"
                        "Examples: 'você deveria perguntar sobre tipo de unha', 'next time ask about X first'\n"
                        "You also have access to RestartConversation to restart after modifications.\n"
                        "Do NOT use these tools for regular conversation or questions about the flow.\n"
                    )

                # Create tool event handler for live flow modification and restart
                def on_tool_event(tool_name: str, metadata: dict[str, Any]) -> bool:
                    if tool_name == "ModifyFlowLive" and is_admin:
                        # Handle live flow modification
                        instruction = metadata.get("instruction", "")
                        if instruction:
                            try:
                                from app.flow_core.live_flow_modification_tool import live_flow_modification_tool_func  # noqa: F401
                                from uuid import UUID  # noqa: F401
                                
                                flow_id = UUID(request.flow_metadata.get("selected_flow_id", ""))
                                with create_session() as mod_session:
                                    result_message = live_flow_modification_tool_func(
                                        instruction=instruction,
                                        flow_id=flow_id,
                                        session=mod_session,
                                        llm=self._llm,
                                        project_context=request.project_context
                                    )
                                    setattr(app_context, "_modification_result", result_message)
                                    return True
                            except Exception as e:
                                logger.exception(f"Live flow modification failed: {e}")
                                setattr(app_context, "_modification_result", "Desculpe, ocorreu um erro ao processar sua instrução.")
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



                # Handle live flow modification tool event
                if result.tool_name == "ModifyFlowLive":
                    modification_message = getattr(app_context, "_modification_result", "Instrução processada.")
                    if hasattr(app_context, "_modification_result"):
                        delattr(app_context, "_modification_result")
                    return FlowResponse(
                        result=FlowProcessingResult.CONTINUE,
                        message=modification_message,
                        context=result.ctx,
                        metadata={"tool_name": result.tool_name, "flow_modified": True},
                    )



                # Map result to response
                if result.escalate:
                    flow_result = FlowProcessingResult.ESCALATE
                elif result.terminal:
                    flow_result = FlowProcessingResult.TERMINAL
                else:
                    flow_result = FlowProcessingResult.CONTINUE

                return FlowResponse(
                    result=flow_result,
                    message=result.assistant_message,
                    context=result.ctx,
                    metadata={
                        "tool_name": result.tool_name,
                        "answers_diff": result.answers_diff,
                    },
                )

        except Exception as e:
            error_msg = f"Flow execution failed: {e!s}"
            raise FlowProcessingError(error_msg, e) from e
