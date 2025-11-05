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
        default=None, 
        description="REQUIRED when action is 'update'. Dictionary mapping field names to their values (e.g., {'tipo_projeto': 'barracão'})"
    )

    target_node_id: str | None = Field(
        default=None, 
        description="REQUIRED when action is 'navigate'. ID of the node to navigate to"
    )

    clarification_reason: str | None = Field(
        default=None, 
        description="Optional when action is 'stay'. Reason why staying on current node"
    )

    handoff_reason: str | None = Field(
        default=None, 
        description="REQUIRED when action is 'handoff'. Explanation for escalating to human agent"
    )

    flow_modification_instruction: str | None = Field(
        default=None,
        description="REQUIRED when action is 'modify_flow' (admin only). Clear instruction for what to modify in the flow",
    )

    flow_modification_target: str | None = Field(
        default=None, description="Target node for flow modification (optional)"
    )

    flow_modification_type: Literal["prompt", "routing", "validation", "general"] | None = Field(
        default=None, description="Type of flow modification (optional)"
    )
    
    updated_communication_style: str | None = Field(
        default=None,
        description="REQUIRED when action is 'update_communication_style' (admin only). COMPLETE new communication style that REPLACES the current style entirely.",
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

    def model_post_init(self, __context: Any) -> None:
        """Validate that required fields are provided based on actions.
        
        This runs after all fields are set, so we can cross-validate.
        """
        # Validate action-specific requirements
        if "update" in self.actions:
            if not self.updates:
                raise ValueError(
                    "CRITICAL: action='update' requires 'updates' field with at least one field-value pair. "
                    "You MUST provide the field name and value you're saving."
                )
        
        if "navigate" in self.actions:
            if not self.target_node_id:
                raise ValueError(
                    "CRITICAL: action='navigate' requires 'target_node_id' field. "
                    "You MUST specify which node to navigate to."
                )
        
        if "handoff" in self.actions:
            if not self.handoff_reason:
                raise ValueError(
                    "CRITICAL: action='handoff' requires 'handoff_reason' field. "
                    "You MUST explain why you're escalating to a human."
                )
        
        if "modify_flow" in self.actions:
            if not self.flow_modification_instruction:
                raise ValueError(
                    "CRITICAL: action='modify_flow' requires 'flow_modification_instruction' field. "
                    "You MUST provide clear instructions on what to modify."
                )
        
        if "update_communication_style" in self.actions:
            if not self.updated_communication_style:
                raise ValueError(
                    "CRITICAL: action='update_communication_style' requires 'updated_communication_style' field. "
                    "You MUST provide the complete new communication style."
                )


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
