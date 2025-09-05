"""Type definitions for the flow core system.

This module contains all type definitions, ensuring strong typing
throughout the flow processing system.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, field_validator

from .constants import (
    DEFAULT_COMPLETION_TYPE,
    DEFAULT_CONFIDENCE,
    DEFAULT_URGENCY,
    MAX_ACKNOWLEDGMENT_LENGTH,
    MAX_CONFIDENCE,
    MAX_CONTEXT_SUMMARY_LENGTH,
    MAX_FOLLOWUP_DELAY_MS,
    MAX_MESSAGE_LENGTH,
    MAX_MESSAGES_ALLOWED,
    MAX_MESSAGES_PER_TURN,
    MAX_NEXT_STEPS,
    MAX_VALIDATION_ERRORS_TO_SHOW,
    MESSAGE_TRUNCATION_LENGTH,
    MIN_CONFIDENCE,
    MIN_FOLLOWUP_DELAY_MS,
    MIN_MESSAGES_PER_TURN,
    NO_DELAY_MS,
    TRUNCATION_SUFFIX,
)


# Message types
class WhatsAppMessage(TypedDict):
    """Type definition for WhatsApp-style messages."""

    text: str
    delay_ms: int


class MessageList(BaseModel):
    """Validated list of WhatsApp messages."""

    messages: list[WhatsAppMessage] = Field(
        ...,
        min_items=MIN_MESSAGES_PER_TURN,
        max_items=MAX_MESSAGES_ALLOWED,
        description="List of messages to send"
    )

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, messages: list[WhatsAppMessage]) -> list[WhatsAppMessage]:
        """Validate message structure and delays."""
        if not messages:
            error_msg = "At least one message is required"
            raise ValueError(error_msg)

        # First message must have 0 delay
        if messages[0].get("delay_ms", NO_DELAY_MS) != NO_DELAY_MS:
            messages[0]["delay_ms"] = NO_DELAY_MS

        # Subsequent messages must have reasonable delays
        for i, msg in enumerate(messages[1:], 1):
            delay = msg.get("delay_ms", MIN_FOLLOWUP_DELAY_MS)
            if delay < MIN_FOLLOWUP_DELAY_MS:
                delay = MIN_FOLLOWUP_DELAY_MS
            elif delay > MAX_FOLLOWUP_DELAY_MS:
                delay = MAX_FOLLOWUP_DELAY_MS
            messages[i]["delay_ms"] = delay

        # Validate text length
        for msg in messages:
            text = msg.get("text", "")
            if len(text) > MAX_MESSAGE_LENGTH:
                # Truncate if too long
                msg["text"] = text[:MESSAGE_TRUNCATION_LENGTH] + TRUNCATION_SUFFIX

        return messages


# Tool response types
class ToolCall(BaseModel):
    """Base model for tool calls from GPT-5."""

    tool_name: str = Field(..., description="Name of the tool to execute")
    confidence: float = Field(
        default=DEFAULT_CONFIDENCE,
        ge=MIN_CONFIDENCE,
        le=MAX_CONFIDENCE,
        description="Confidence in this tool selection"
    )
    reasoning: str = Field(..., description="Reasoning for this tool choice")


class UpdateAnswersCall(ToolCall):
    """Tool call for UpdateAnswers."""

    tool_name: Literal["UpdateAnswers"] = "UpdateAnswers"
    updates: dict[str, Any] = Field(
        ...,
        min_items=1,
        description="Updates to apply to answers"
    )
    validated: bool = Field(default=True)


class StayOnThisNodeCall(ToolCall):
    """Tool call for StayOnThisNode."""

    tool_name: Literal["StayOnThisNode"] = "StayOnThisNode"
    acknowledgment: str | None = Field(default=None, max_length=MAX_ACKNOWLEDGMENT_LENGTH)
    clarification_reason: Literal[
        "unclear_response",
        "off_topic",
        "needs_explanation",
        "format_clarification"
    ] = Field(...)


class NavigateToNodeCall(ToolCall):
    """Tool call for NavigateToNode."""

    tool_name: Literal["NavigateToNode"] = "NavigateToNode"
    target_node_id: str = Field(...)
    navigation_type: Literal["next", "skip", "back", "jump"] = Field(...)


class RequestHumanHandoffCall(ToolCall):
    """Tool call for RequestHumanHandoff."""

    tool_name: Literal["RequestHumanHandoff"] = "RequestHumanHandoff"
    reason: Literal[
        "user_frustrated",
        "explicit_request",
        "too_complex",
        "technical_issue"
    ] = Field(...)
    context_summary: str = Field(..., max_length=MAX_CONTEXT_SUMMARY_LENGTH)
    urgency: Literal["low", "medium", "high"] = Field(default=DEFAULT_URGENCY)


class ConfirmCompletionCall(ToolCall):
    """Tool call for ConfirmCompletion."""

    tool_name: Literal["ConfirmCompletion"] = "ConfirmCompletion"
    summary: dict[str, Any] = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list, max_items=MAX_NEXT_STEPS)
    completion_type: Literal["success", "partial", "abandoned"] = Field(default=DEFAULT_COMPLETION_TYPE)


class RestartConversationCall(ToolCall):
    """Tool call for RestartConversation."""

    tool_name: Literal["RestartConversation"] = "RestartConversation"
    clear_history: bool = Field(default=True)


# Union type for all possible tool calls
ToolCallUnion = (
    UpdateAnswersCall
    | StayOnThisNodeCall
    | NavigateToNodeCall
    | RequestHumanHandoffCall
    | ConfirmCompletionCall
    | RestartConversationCall
)


# GPT-5 response schema
class GPT5Response(BaseModel):
    """Complete response from GPT-5 including tool and messages."""

    tool: ToolCallUnion = Field(..., description="Tool to execute")
    messages: list[WhatsAppMessage] = Field(
        ...,
        min_items=MIN_MESSAGES_PER_TURN,
        max_items=MAX_MESSAGES_PER_TURN,
        description="Natural WhatsApp messages to send"
    )
    reasoning: str = Field(..., description="Overall reasoning for the response")

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, messages: list[WhatsAppMessage]) -> list[WhatsAppMessage]:
        """Ensure messages are properly structured."""
        validator = MessageList(messages=messages)
        return validator.messages

    def get_tool_name(self) -> str:
        """Get the name of the selected tool."""
        return self.tool.tool_name

    def get_tool_data(self) -> dict[str, Any]:
        """Get tool data as a dictionary."""
        return self.tool.model_dump(exclude={"tool_name"})


# Flow state types
class ConversationTurn(TypedDict):
    """Type for conversation history turns."""

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str | None
    node_id: str | None
    metadata: dict[str, Any] | None


class FlowState(TypedDict):
    """Type for flow state summary."""

    answers: dict[str, Any]
    pending_field: str | None
    active_path: str | None
    clarification_count: int
    path_corrections: int
    is_complete: bool


# Error types
class GPT5SchemaError(Exception):
    """Raised when GPT-5 response doesn't match expected schema."""

    def __init__(
        self,
        message: str,
        raw_response: dict[str, Any] | None,
        validation_errors: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.validation_errors = validation_errors or []


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    def __init__(
        self,
        tool_name: str,
        message: str,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.original_error = original_error


# Validation helpers
def _create_unknown_tool_error(
    tool_name: str,
    raw_response: dict[str, Any],
) -> GPT5SchemaError:
    """Create error for unknown tool name."""
    error_msg = f"Unknown tool name: {tool_name}"
    validation_errors = [f"Tool '{tool_name}' is not recognized"]
    return GPT5SchemaError(error_msg, raw_response, validation_errors)


def _create_validation_error(
    exception: Exception,
    raw_response: dict[str, Any],
) -> GPT5SchemaError:
    """Create error for validation failure."""
    error_msg = f"Failed to validate GPT-5 response: {exception}"
    validation_errors = []
    if hasattr(exception, "errors"):
        validation_errors = [str(err) for err in exception.errors()][:MAX_VALIDATION_ERRORS_TO_SHOW]
    return GPT5SchemaError(error_msg, raw_response, validation_errors)


def validate_gpt5_response(raw_response: dict[str, Any]) -> GPT5Response:
    """Validate and parse a GPT-5 response.

    Args:
        raw_response: Raw dictionary from GPT-5

    Returns:
        Validated GPT5Response

    Raises:
        GPT5SchemaError: If validation fails
    """
    try:
        # First try to parse the tool
        tool_data = raw_response.get("tool", {})
        tool_name = tool_data.get("tool_name", "")

        # Create the appropriate tool model
        tool_model: ToolCallUnion
        if tool_name == "UpdateAnswers":
            tool_model = UpdateAnswersCall(**tool_data)
        elif tool_name == "StayOnThisNode":
            tool_model = StayOnThisNodeCall(**tool_data)
        elif tool_name == "NavigateToNode":
            tool_model = NavigateToNodeCall(**tool_data)
        elif tool_name == "RequestHumanHandoff":
            tool_model = RequestHumanHandoffCall(**tool_data)
        elif tool_name == "ConfirmCompletion":
            tool_model = ConfirmCompletionCall(**tool_data)
        elif tool_name == "RestartConversation":
            tool_model = RestartConversationCall(**tool_data)
        else:
            raise _create_unknown_tool_error(tool_name, raw_response)

        # Create the full response
        return GPT5Response(
            tool=tool_model,
            messages=raw_response.get("messages", []),
            reasoning=raw_response.get("reasoning", ""),
        )

    except Exception as e:
        if isinstance(e, GPT5SchemaError):
            raise

        raise _create_validation_error(e, raw_response) from e


# Type aliases for common patterns
AnswersDict = dict[str, Any]
MetadataDict = dict[str, Any]
ToolName = Literal[
    "UpdateAnswers",
    "StayOnThisNode",
    "NavigateToNode",
    "RequestHumanHandoff",
    "ConfirmCompletion",
    "RestartConversation"
]
