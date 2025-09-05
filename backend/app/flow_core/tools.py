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


class StayOnThisNode(FlowTool):
    """Stay on the current node and repeat/clarify the current question.

    Use this when:
    - User needs clarification about the question
    - User's response was unclear or off-topic
    - You need to acknowledge something before repeating the question
    - User asks about format/units but still needs to answer
    """

    acknowledgment: str | None = Field(
        default=None,
        max_length=MAX_ACKNOWLEDGMENT_LENGTH,
        description="Optional brief acknowledgment before repeating the question"
    )
    clarification_reason: Literal[
        "unclear_response",
        "off_topic",
        "needs_explanation",
        "format_clarification"
    ] = Field(
        ...,
        description="Why we're staying on this node"
    )


class NavigateToNode(FlowTool):
    """Navigate to a specific node in the flow.

    Use this when:
    - User wants to skip the current question
    - User wants to go back to a previous question
    - Flow logic requires jumping to a specific node
    - Following a decision path to the next node
    """

    target_node_id: str = Field(
        ...,
        description="The ID of the node to navigate to"
    )
    navigation_type: Literal[
        "next",
        "skip",
        "back",
        "jump"
    ] = Field(
        ...,
        description="Type of navigation being performed"
    )


class UpdateAnswers(FlowTool):
    """Update one or more answers in the flow state.

    CRITICAL: The 'updates' field is MANDATORY and must contain at least one key-value pair.
    The key should be the field name and the value should be the extracted answer.

    Use this when:
    - User provides an answer to the current question
    - User corrects a previous answer
    - Multiple answers can be extracted from a single response
    """

    updates: dict[str, Any] = Field(
        ...,
        min_items=MIN_DICT_ITEMS,
        description="Key-value pairs to update in the answers map"
    )

    @field_validator("updates")
    @classmethod
    def validate_updates(cls, updates: dict[str, Any]) -> dict[str, Any]:
        """Ensure updates is not empty."""
        if not updates:
            error_msg = "Updates must contain at least one key-value pair"
            raise ValueError(error_msg)
        return updates

    validated: bool = Field(
        default=True,
        description="Whether the answers have been validated against constraints"
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


class ConfirmCompletion(FlowTool):
    """Confirm that the flow has been completed successfully.

    Use this when:
    - All required information has been collected
    - The flow reaches a terminal node
    - User explicitly ends the conversation
    """

    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary of collected information"
    )

    next_steps: list[str] = Field(
        default_factory=list,
        max_items=MAX_NEXT_STEPS,
        description="Next steps for the user"
    )

    completion_type: Literal["success", "partial", "abandoned"] = Field(
        default=DEFAULT_COMPLETION_TYPE,
        description="Type of completion"
    )


class RestartConversation(FlowTool):
    """Completely restart the conversation from the beginning.

    Use this ONLY when:
    - User explicitly says "restart", "start over", "begin again"
    - User clearly wants to reset everything and start fresh

    This will clear all answers and return to the entry node.
    """

    clear_history: bool = Field(
        default=True,
        description="Whether to clear conversation history"
    )


# Tool registry - only essential tools
FLOW_TOOLS = [
    StayOnThisNode,
    NavigateToNode,
    UpdateAnswers,
    RequestHumanHandoff,
    ConfirmCompletion,
    RestartConversation,
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
