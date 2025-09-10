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

    @field_validator("messages")  # type: ignore[misc]
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
    messages: list[WhatsAppMessage] = Field(
        ...,
        min_items=MIN_MESSAGES_PER_TURN,
        max_items=MAX_MESSAGES_ALLOWED,
        description="WhatsApp messages to send to user"
    )
    confidence: float = Field(
        default=DEFAULT_CONFIDENCE,
        ge=MIN_CONFIDENCE,
        le=MAX_CONFIDENCE,
        description="Confidence in this tool selection"
    )
    reasoning: str = Field(..., description="Reasoning for this tool choice")


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


class ModifyFlowLiveCall(ToolCall):
    """Tool call for ModifyFlowLive (admin only)."""

    tool_name: Literal["ModifyFlowLive"] = "ModifyFlowLive"
    instruction: str = Field(..., description="The modification instruction")
    target_node: str | None = Field(default=None, description="Target node to modify")
    modification_type: Literal["prompt", "routing", "validation", "general"] = Field(
        default="general",
        description="Type of modification"
    )




class PerformActionCall(ToolCall):
    """Tool call for unified PerformAction."""
    
    tool_name: Literal["PerformAction"] = "PerformAction"
    actions: list[Literal["stay", "update", "navigate", "handoff", "complete", "restart"]] = Field(
        ...,
        description="Actions to take in sequence (e.g., ['update', 'navigate'])"
    )
    # messages field inherited from ToolCall
    updates: dict[str, Any] | None = Field(default=None)
    target_node_id: str | None = Field(default=None)
    clarification_reason: str | None = Field(default=None)
    handoff_reason: str | None = Field(default=None)


# Union type for all possible tool calls
ToolCallUnion = (
    PerformActionCall
    | RequestHumanHandoffCall
    | ModifyFlowLiveCall
)


# GPT-5 response schema
class GPT5Response(BaseModel):
    """Complete response from GPT-5 including tools only."""

    tools: list[ToolCallUnion] = Field(
        ..., 
        min_items=1,
        max_items=3,  # Allow up to 3 tool calls per turn
        description="Tools to execute in sequence"
    )
    reasoning: str = Field(..., description="Overall reasoning for the response")

    def get_tool_name(self) -> str:
        """Get the primary tool name from the response (first tool)."""
        return self.tools[0].tool_name if self.tools else "PerformAction"
    
    def get_all_tool_names(self) -> list[str]:
        """Get all tool names from the response."""
        return [tool.tool_name for tool in self.tools]

    def get_tool_data(self) -> dict[str, Any]:
        """Get primary tool-specific data as dictionary (first tool)."""
        if not self.tools:
            return {}
        result = self.tools[0].model_dump(exclude={"tool_name", "messages"})
        return dict(result) if result is not None else {}
    
    def get_all_tools_data(self) -> list[tuple[str, dict[str, Any]]]:
        """Get all tools with their data."""
        tools_data = []
        for tool in self.tools:
            data = tool.model_dump(exclude={"tool_name", "messages"})
            tools_data.append((tool.tool_name, dict(data) if data else {}))
        return tools_data


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


def _create_tool_model(tool_name: str, tool_data: dict[str, Any]) -> ToolCallUnion:
    """Create the appropriate tool model based on tool name."""
    if tool_name == "PerformAction":
        return PerformActionCall(**tool_data)
    if tool_name == "RequestHumanHandoff":
        return RequestHumanHandoffCall(**tool_data)
    if tool_name == "ModifyFlowLive":
        return ModifyFlowLiveCall(**tool_data)

    msg = f"Unknown tool name: {tool_name}"
    validation_errors = [f"Tool '{tool_name}' is not recognized"]
    raise GPT5SchemaError(msg, None, validation_errors)


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
        # Handle both single tool (legacy) and multiple tools
        tools_list = []
        
        # Check for new format (multiple tools)
        if "tools" in raw_response:
            for tool_data in raw_response["tools"]:
                tool_name = tool_data.get("tool_name", "")
                tool_model = _create_tool_model(tool_name, tool_data)
                tools_list.append(tool_model)
        # Handle legacy single tool format
        elif "tool" in raw_response:
            tool_data = raw_response["tool"]
            tool_name = tool_data.get("tool_name", "")
            tool_model = _create_tool_model(tool_name, tool_data)
            tools_list.append(tool_model)
        else:
            # Default fallback
            tools_list.append(_create_tool_model("PerformAction", {
                "reasoning": "No tool specified",
                "actions": ["stay"],
                "clarification_reason": "unclear_response",
                "messages": [{"text": "Como posso ajudar?", "delay_ms": 0}]
            }))

        # Create the full response
        return GPT5Response(
            tools=tools_list,
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
    "PerformAction",
    "RequestHumanHandoff",
    "ModifyFlowLive"
]
