"""Enhanced tool schemas for LLM-oriented flow interactions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FlowResponse(BaseModel):
    """Base class for all flow response tools."""

    confidence: float = Field(
        default=1.0,
        description="Confidence level in this response (0-1)",
    )


class UpdateAnswersFlow(FlowResponse):
    """Update one or more answers in the flow state."""

    updates: dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value updates for the answers map",
    )
    validated: bool = Field(
        default=True,
        description="Whether the answers have been validated",
    )


class ClarifyQuestion(FlowResponse):
    """Request clarification about the current question."""

    clarification_type: Literal["meaning", "options", "purpose", "format"] = Field(
        default="meaning",
        description="Type of clarification needed",
    )
    original_question: str | None = Field(
        default=None,
        description="The question being clarified",
    )


class SkipQuestion(FlowResponse):
    """Skip the current question (if allowed by flow policy)."""

    reason: Literal["not_applicable", "unknown", "prefer_not_to_answer", "will_answer_later"] = (
        Field(
            ...,
            description="Reason for skipping",
        )
    )
    skip_to: str | None = Field(
        default=None,
        description="Optional node ID to skip to",
    )


class RevisitQuestion(FlowResponse):
    """Go back to a previous question to change the answer."""

    question_key: str = Field(
        ...,
        description="Key of the question to revisit",
    )
    revisit_value: str | None = Field(
        default=None,
        description="The new value for the question (extract from user's message if possible)",
    )
    reason: str | None = Field(
        default=None,
        description="Why the user wants to revisit",
    )


class SelectFlowPath(FlowResponse):
    """Select a path in a multi-path flow."""

    path: str | None = Field(
        default=None,
        description="Name of the selected path or null if none applies",
    )
    confidence: float = Field(
        default=0.5,
        description="Confidence in path selection (0-1)",
    )
    reasoning: str | None = Field(
        default=None,
        description="Reasoning for path selection",
    )


class RequestHumanHandoff(FlowResponse):
    """Request handoff to a human agent."""

    reason: Literal[
        "complex_request",
        "technical_issue",
        "user_frustration",
        "out_of_scope",
        "explicit_request",
        "policy_violation",
    ] = Field(
        ...,
        description="Categorized reason for handoff",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured context for the human agent",
    )
    urgency: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Urgency level of the handoff",
    )


class ProvideInformation(FlowResponse):
    """Provide information without updating answers."""

    information_type: Literal["help", "status", "context", "example"] = Field(
        ...,
        description="Type of information being provided",
    )
    related_to: str | None = Field(
        default=None,
        description="Question key this information relates to",
    )


class ConfirmCompletion(FlowResponse):
    """Confirm flow completion and summarize."""

    summary: dict[str, Any] = Field(
        ...,
        description="Summary of collected information",
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="Next steps for the user",
    )
    completion_type: Literal["success", "partial", "abandoned"] = Field(
        default="success",
        description="Type of completion",
    )


class NavigateFlow(FlowResponse):
    """Navigate to a specific point in the flow."""

    target_node: str | None = Field(
        default=None,
        description="Target node ID to navigate to",
    )
    navigation_type: Literal["next", "previous", "jump", "restart"] = Field(
        ...,
        description="Type of navigation",
    )


class RestartConversation(FlowResponse):
    """Hard reset of the conversation/flow context to the very beginning.

    This tool MUST be used only when the user explicitly and unequivocally asks to
    "restart from scratch" or to "start over" the conversation. It clears answers,
    history, path selections and returns to the flow's entry node.
    """

    reason: Literal["explicit_user_request",] = Field(
        default="explicit_user_request", description="Why the restart is being performed."
    )


# Tool registry for flow interactions
FLOW_TOOLS = [
    UpdateAnswersFlow,
    ClarifyQuestion,
    SkipQuestion,
    RevisitQuestion,
    SelectFlowPath,
    RequestHumanHandoff,
    ProvideInformation,
    ConfirmCompletion,
    NavigateFlow,
    RestartConversation,
]


# Legacy aliases (for migration only)
UpdateAnswers = UpdateAnswersFlow
SelectPath = SelectFlowPath
EscalateToHuman = RequestHumanHandoff


class UnknownAnswer(FlowResponse):
    """User doesn't know the answer or needs clarification."""

    field: str | None = Field(
        default=None,
        description="Field key that the user explicitly does not know; if null, assume the pending field",
    )
    reason: Literal["unknown", "clarification_needed", "not_applicable"] = Field(
        default="unknown",
        description="Reason for unknown answer",
    )
