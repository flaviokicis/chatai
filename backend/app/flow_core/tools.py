"""Simplified tool schemas for flow interactions.

This module contains only the essential tools needed for flow navigation and control.
Each tool has a single, clear responsibility.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .constants import (
    DEFAULT_CONFIDENCE,
    MAX_CONFIDENCE,
    MIN_CONFIDENCE,
)


class FlowTool(BaseModel):
    """Base class for all flow tools with common metadata."""

    confidence: float = Field(
        default=DEFAULT_CONFIDENCE,
        ge=MIN_CONFIDENCE,
        le=MAX_CONFIDENCE,
        description="Confidence level in this action (0-1)",
    )
    reasoning: str = Field(..., description="Brief explanation of why this tool was chosen")


class PerformAction(FlowTool):
    """Unified action tool that combines all necessary actions and messages.

    This tool handles the complete response including:
    - Staying on current node or navigating
    - Updating answers if needed
    - Sending messages to the user
    - Modifying the flow (admin only)
    - Updating communication style (admin only)

    ALWAYS use this tool for any response.
    """

    actions: list[
        Literal["stay", "update", "navigate", "handoff", "complete", "restart", "modify_flow", "update_communication_style"]
    ] = Field(
        ...,
        description="Actions to take in sequence (e.g., ['update', 'navigate'] to save answer then navigate)",
    )

    messages: list[dict[str, Any]] = Field(
        description="WhatsApp messages to send to the user", min_length=1, max_length=5
    )

    updates: dict[str, Any] | None = Field(
        default=None, description="Field updates when action is 'update'"
    )

    target_node_id: str | None = Field(
        default=None, description="Target node when action is 'navigate'"
    )

    clarification_reason: str | None = Field(
        default=None, description="Reason when action is 'stay'"
    )

    handoff_reason: str | None = Field(default=None, description="Reason when action is 'handoff'")

    flow_modification_instruction: str | None = Field(
        default=None,
        description="Instruction for modifying the flow when action is 'modify_flow' (admin only)",
    )

    flow_modification_target: str | None = Field(
        default=None, description="Target node for flow modification (optional)"
    )

    flow_modification_type: Literal["prompt", "routing", "validation", "general"] | None = Field(
        default=None, description="Type of flow modification (optional)"
    )
    
    updated_communication_style: str | None = Field(
        default=None,
        description="COMPLETE new communication style when action is 'update_communication_style' (admin only). This REPLACES the current style entirely.",
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
]


def get_tool_by_name(name: str) -> type[FlowTool] | None:
    """Get a tool class by its name."""
    for tool in FLOW_TOOLS:
        if tool.__name__ == name:
            return tool
    return None


def get_tool_description(tool_name: str) -> str:
    """Get the description of a tool from its docstring."""
    tool_class = get_tool_by_name(tool_name)
    if tool_class and tool_class.__doc__:
        return tool_class.__doc__.strip()
    return ""
