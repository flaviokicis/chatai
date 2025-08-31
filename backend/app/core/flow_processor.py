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
from uuid import UUID

from app.core.thought_tracer import DatabaseThoughtTracer
from app.db.session import create_session
from app.flow_core.compiler import compile_flow
from app.flow_core.ir import Flow
from app.flow_core.runner import FlowTurnRunner
from app.flow_core.state import FlowContext
from app.flow_core.tool_schemas import EnterTrainingMode

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

logger = logging.getLogger(__name__)


class FlowProcessingResult(Enum):
    """Result types for flow processing."""

    CONTINUE = "continue"
    TERMINAL = "terminal"
    ESCALATE = "escalate"
    TRAINING_MODE = "training_mode"
    ERROR = "error"


@dataclass(frozen=True)
class FlowRequest:
    """Immutable request for flow processing."""

    user_id: str
    user_message: str
    flow_definition: dict[str, Any]
    flow_metadata: dict[str, Any]  # flow_name, flow_id, etc.
    tenant_id: UUID
    project_context: ProjectContext


@dataclass(frozen=True)
class FlowResponse:
    """Immutable response from flow processing."""

    result: FlowProcessingResult
    message: str | None
    context: FlowContext | None
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


class TrainingModeHandler(Protocol):
    """Interface for handling training mode operations."""

    async def handle_training_request(
        self,
        request: FlowRequest,
        session_id: str,
        app_context: Any,
    ) -> FlowResponse | None:
        """Handle training mode if active, return None if not in training mode."""
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
        training_handler: TrainingModeHandler | None = None,
        thread_updater: ThreadStatusUpdater | None = None,
    ) -> None:
        """
        Initialize the flow processor.
        
        Args:
            llm: LLM client for flow processing
            session_manager: Session and context management
            training_handler: Optional training mode handler
            thread_updater: Optional thread status updater
        """
        self._llm = llm
        self._session_manager = session_manager
        self._training_handler = training_handler
        self._thread_updater = thread_updater

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
                # Step 2: Check training mode
                if self._training_handler:
                    training_response = await self._training_handler.handle_training_request(
                        request, session_id, app_context
                    )
                    if training_response:
                        return training_response

                # Step 3: Process through flow engine
                flow_response = await self._execute_flow(request, session_id, app_context)

                # Step 4: Update thread status if needed
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
            logger.error("Flow processing failed for user %s: %s", request.user_id, e)
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

                # Create tool event handler for training mode
                def on_tool_event(tool_name: str, metadata: dict[str, Any]) -> bool:
                    if tool_name == "EnterTrainingMode":
                        # Store training prompt for response
                        prompt = "Para entrar no modo treino, informe a senha."
                        self._session_manager.clear_context(session_id)
                        app_context._training_prompt = prompt
                        return True
                    return False

                # Create and run flow
                runner = FlowTurnRunner(
                    compiled_flow=compiled_flow,
                    llm=self._llm,
                    strict_mode=True,
                    thought_tracer=thought_tracer,
                    extra_tools=[EnterTrainingMode],
                    instruction_prefix=(
                        "IMPORTANT: You may ONLY call EnterTrainingMode when the user explicitly mentions\n"
                        "phrases like 'modo teste', 'modo treino', 'ativar modo de treinamento', or clear\n"
                        "equivalents in Portuguese. Do NOT infer or guess. If not explicit, do NOT call it."
                    ),
                    on_tool_event=on_tool_event,
                )

                # Initialize context
                ctx = runner.initialize_context(existing_context)
                ctx.user_id = request.user_id
                ctx.session_id = session_id
                ctx.tenant_id = request.tenant_id

                # Process the turn
                result = runner.process_turn(
                    ctx=ctx,
                    user_message=request.user_message,
                    project_context=request.project_context
                )

                # Handle training mode tool event
                if result.tool_name == "EnterTrainingMode":
                    prompt = getattr(app_context, "_training_prompt", "Para entrar no modo treino, informe a senha.")
                    if hasattr(app_context, "_training_prompt"):
                        delattr(app_context, "_training_prompt")
                    return FlowResponse(
                        result=FlowProcessingResult.TRAINING_MODE,
                        message=prompt,
                        context=result.ctx,
                        metadata={"tool_name": result.tool_name},
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
            raise FlowProcessingError(f"Flow execution failed: {e}", e) from e
