"""Typed result objects for flow processing to improve type safety.

This module provides typed alternatives to raw dictionaries for flow processing results,
enabling better IDE support, validation, and maintainability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from ..core.message_metadata import OutboundMessageMetadata
from ..flow_core.actions import ActionResult


@dataclass(slots=True)
class ToolExecutionResult:
    """Result of tool execution with typed fields."""

    # Basic execution info
    tool_name: str
    success: bool
    execution_time_ms: float | None = None

    # Tool arguments and results
    arguments: dict[str, Any] = field(default_factory=dict)
    result_data: dict[str, Any] = field(default_factory=dict)

    # External action results, if any
    external_action_executed: bool = False
    external_action_result: ActionResult | None = None

    # Error information
    error_message: str | None = None
    error_code: str | None = None

    # Retry information
    attempt_number: int = 1
    max_attempts: int = 3

    # Context
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def requires_llm_feedback(self) -> bool:
        """Check if this result requires LLM feedback."""
        return self.external_action_executed and self.external_action_result is not None


@dataclass(slots=True)
class FlowProcessingResult:
    """Result of flow processing with comprehensive typed information."""

    # Processing status
    success: bool
    terminal: bool = False
    escalate: bool = False

    # Response content
    assistant_message: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)

    # Tool execution details
    tool_executions: list[ToolExecutionResult] = field(default_factory=list)

    # Flow state changes
    answers_diff: dict[str, Any] = field(default_factory=dict)

    # Flow control
    next_node_id: str | None = None
    flow_completed: bool = False

    # External action results
    external_actions_executed: list[str] = field(default_factory=list)
    external_action_results: dict[str, Any] = field(default_factory=dict)

    # Response quality and metadata
    confidence: float = 1.0
    reasoning: str | None = None
    processing_duration_ms: float | None = None

    # Error handling
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Metadata
    metadata: OutboundMessageMetadata = field(default_factory=OutboundMessageMetadata)

    @property
    def primary_tool_result(self) -> ToolExecutionResult | None:
        """Get the primary (first) tool execution result."""
        return self.tool_executions[0] if self.tool_executions else None

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return bool(self.errors) or any(not te.success for te in self.tool_executions)

    @property
    def successful_tools(self) -> list[ToolExecutionResult]:
        """Get list of successful tool executions."""
        return [te for te in self.tool_executions if te.success]

    @property
    def failed_tools(self) -> list[ToolExecutionResult]:
        """Get list of failed tool executions."""
        return [te for te in self.tool_executions if not te.success]


@dataclass(slots=True)
class ActionExecutionResult:
    """Result of external action execution."""

    # Action identification
    action_name: str
    action_id: str | None = None

    # Execution status
    executed: bool = False
    successful: bool | None = None

    # Timing
    started_at: float | None = None
    completed_at: float | None = None
    duration_ms: float | None = None

    # Results
    result_data: dict[str, Any] = field(default_factory=dict)
    response_message: str | None = None

    # Error information
    error_message: str | None = None
    error_type: str | None = None

    # Context and metadata
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """Check if action execution is complete."""
        return self.executed and self.successful is not None


@dataclass(slots=True)
class FlowStateChange:
    """Represents a change in flow state."""

    # Change identification
    change_type: str  # answer_added, answer_updated, context_updated, etc.
    field_name: str

    # Values
    old_value: Any = None
    new_value: Any = None

    # Metadata
    timestamp: float | None = None
    source: str | None = None  # llm, user, system, etc.

    # Validation
    validated: bool = True
    validation_errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResponseGenerationResult:
    """Result of response generation process."""

    # Generated content
    messages: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str | None = None

    # Generation metadata
    model_used: str | None = None
    tokens_consumed: int = 0
    generation_time_ms: float | None = None

    # Quality metrics
    confidence: float = 1.0
    coherence_score: float | None = None

    # Tool calls made during generation
    tool_calls_requested: list[str] = field(default_factory=list)

    # Context used
    context_length: int = 0
    context_truncated: bool = False

    # Error information
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_messages(self) -> bool:
        """Check if any messages were generated."""
        return bool(self.messages)

    @property
    def message_count(self) -> int:
        """Get the number of messages generated."""
        return len(self.messages)

    @property
    def total_text_length(self) -> int:
        """Get total length of all message text."""
        return sum(len(msg.get("text", "")) for msg in self.messages)


@dataclass(slots=True)
class FlowExecutionContext:
    """Context information for flow execution."""

    # Flow identification
    flow_id: UUID
    flow_version: str | None = None
    current_node_id: str | None = None

    # Session information
    session_id: str | None = None
    user_id: str | None = None
    tenant_id: UUID | None = None

    # Channel context
    channel_type: str | None = None
    channel_instance_id: UUID | None = None

    # Conversation context
    thread_id: UUID | None = None
    message_count: int = 0
    turn_number: int = 0

    # Flow state
    collected_answers: dict[str, Any] = field(default_factory=dict)
    flow_context: dict[str, Any] = field(default_factory=dict)

    # Processing flags
    is_admin: bool = False
    debug_mode: bool = False

    # Timing
    started_at: float | None = None
    last_activity_at: float | None = None
