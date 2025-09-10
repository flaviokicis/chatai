"""Simplified tool schemas for flow interactions.

This module contains only the essential tools needed for flow navigation and control.
Each tool has a single, clear responsibility following FAANG-level architecture principles.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .constants import (
    DEFAULT_COMPLETION_TYPE,
    DEFAULT_CONFIDENCE,
    DEFAULT_URGENCY,
    MAX_ACKNOWLEDGMENT_LENGTH,
    MAX_CONFIDENCE,
    MAX_CONTEXT_SUMMARY_LENGTH,
    MAX_NEXT_STEPS,
    MIN_CONFIDENCE,
    MIN_DICT_ITEMS,
)


class FlowTool(BaseModel):
    """Base class for all flow tools with common metadata."""

    confidence: float = Field(
        default=DEFAULT_CONFIDENCE,
        ge=MIN_CONFIDENCE,
        le=MAX_CONFIDENCE,
        description="Confidence level in this action (0-1)"
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of why this tool was chosen"
    )


class RequestHumanHandoff(FlowTool):
    """Request handoff to a human agent.

    Use this when:
    - User is frustrated or confused after multiple attempts
    - User explicitly asks to speak to a human
    - The request is too complex for the flow
    - Technical issues prevent progress
    """

    reason: Literal[
        "user_frustrated",
        "explicit_request",
        "too_complex",
        "technical_issue"
    ] = Field(
        ...,
        description="Categorized reason for handoff"
    )

    context_summary: str = Field(
        ...,
        max_length=MAX_CONTEXT_SUMMARY_LENGTH,
        description="Brief summary of the conversation for the human agent"
    )

    urgency: Literal["low", "medium", "high"] = Field(
        default=DEFAULT_URGENCY,
        description="Urgency level of the handoff"
    )


class ModifyFlowLive(FlowTool):
    """Modify the current flow based on admin instructions during conversation.
    
    ADMIN ONLY TOOL - Use this when an admin user wants to:
    - Change how the flow behaves
    - Add or modify questions
    - Adjust flow logic or routing
    - Update prompts or messages
    
    The modification will be stored and applied to future conversations.
    """
    
    instruction: str = Field(
        ...,
        description="The specific instruction about how to modify the flow behavior"
    )
    
    target_node: str | None = Field(
        default=None,
        description="Specific node to modify (if applicable)"
    )
    
    modification_type: Literal["prompt", "routing", "validation", "general"] = Field(
        default="general",
        description="Type of modification being requested"
    )


class PerformAction(FlowTool):
    """Unified action tool that combines all necessary actions and messages.
    
    This tool handles the complete response including:
    - Staying on current node or navigating
    - Updating answers if needed
    - Sending messages to the user
    
    ALWAYS use this tool for any response.
    """
    
    actions: list[Literal["stay", "update", "navigate", "handoff", "complete", "restart"]] = Field(
        ...,
        description="Actions to take in sequence (e.g., ['update', 'navigate'] to save answer then navigate)"
    )
    
    messages: list[dict[str, Any]] = Field(
        ...,
        min_items=1,
        max_items=5,
        description="WhatsApp messages to send to the user"
    )
    
    # Optional fields based on action
    updates: dict[str, Any] | None = Field(
        default=None,
        description="Field updates when action is 'update'"
    )
    
    target_node_id: str | None = Field(
        default=None,
        description="Target node when action is 'navigate'"
    )
    
    clarification_reason: str | None = Field(
        default=None,
        description="Reason when action is 'stay'"
    )
    
    handoff_reason: str | None = Field(
        default=None,
        description="Reason when action is 'handoff'"
    )
    
    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate message structure."""
        for msg in v:
            if "text" not in msg or not msg["text"]:
                raise ValueError("Each message must have a non-empty 'text' field")
            if "delay_ms" not in msg:
                msg["delay_ms"] = 0
        return v


# Tool registry - only essential tools
FLOW_TOOLS = [
    PerformAction,
    RequestHumanHandoff,
]

# Admin-only tools (not included in default registry)
ADMIN_TOOLS = [
    ModifyFlowLive,
]


def get_tool_by_name(name: str) -> type[FlowTool] | None:
    """Get a tool class by its name."""
    # Check regular tools first
    for tool in FLOW_TOOLS:
        if tool.__name__ == name:
            return tool
    # Then check admin tools
    for tool in ADMIN_TOOLS:
        if tool.__name__ == name:
            return tool
    return None


def get_tool_description(tool_name: str) -> str:
    """Get the description of a tool from its docstring."""
    tool_class = get_tool_by_name(tool_name)
    if tool_class and tool_class.__doc__:
        return tool_class.__doc__.strip()
    return ""
