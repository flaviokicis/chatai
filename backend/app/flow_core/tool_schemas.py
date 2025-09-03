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
    reasoning: str | None = Field(
        default=None,
        description=(
            "Brief explanation (one sentence) of why this tool was chosen and how the user's"
            " message and context support the decision. Used for debugging/telemetry only;"
            " never shown directly to the user."
        ),
    )


class UpdateAnswersFlow(FlowResponse):
    """Update one or more answers in the flow state."""

    updates: dict[str, Any] = Field(
        ...,
        description="Key-value updates for the answers map - REQUIRED field that must contain at least one update",
    )
    validated: bool = Field(
        default=True,
        description="Whether the answers have been validated",
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
    ack_message: str | None = Field(
        default=None,
        description=(
            "Optional short acknowledgement or brief informative sentence (max ~140 chars) "
            "to show before the next question. Must not add new business details beyond "
            "what the user explicitly asked; keep it concise and neutral."
        ),
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


class PathCorrection(FlowResponse):
    """Correct a previously selected path in the flow.

    Use this when the user is correcting a path choice they made earlier,
    typically with phrases like "actually it's...", "I meant...", "sorry, it's...".
    This is different from RevisitQuestion which is for changing answer values.
    """

    corrected_path: str = Field(
        ...,
        description="The corrected path - choose EXACTLY from the available flow paths list. Do not use the raw user description, but the actual path name from available options."
    )
    original_path: str | None = Field(
        default=None,
        description="The original path that was selected (if known)"
    )
    confidence: float = Field(
        default=0.8,
        description="Confidence in the path correction (0-1)"
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


# Live flow modification tool (only available to admin users)
class ModifyFlowLive(FlowResponse):
    """Modify the current flow based on admin instructions during conversation.

    STRICT USAGE RULE:
    - Use ONLY when user gives clear instructions about how the flow should behave differently
    - Examples: "você deveria perguntar sobre tipo de unha", "next time ask about X first"
    - Do NOT use for regular conversation or questions about the flow
    - Only available when user is an admin (phone number in admin list)
    """

    instruction: str = Field(
        description="The specific instruction about how to modify the flow behavior"
    )
    reason: Literal["admin_instruction"] = Field(
        default="admin_instruction",
        description="Reason for the modification",
    )





# Tool registry for flow interactions
FLOW_TOOLS = [
    UpdateAnswersFlow,
    SkipQuestion,
    RevisitQuestion,
    SelectFlowPath,
    PathCorrection,
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
    """User doesn't know the answer, needs clarification, or is confused."""

    field: str | None = Field(
        default=None,
        description="Field key that the user explicitly does not know; if null, assume the pending field",
    )
    reason: Literal["clarification_needed", "incoherent_or_confused", "requested_by_user"] = Field(
        default="clarification_needed",
        description=(
            "Reason for unknown answer:\n"
            "- clarification_needed: User asks 'what do you mean?', 'como assim?', needs question explained\n"
            "- incoherent_or_confused: User gives nonsensical/unrelated response, seems lost or confused\n"
            "- requested_by_user: User explicitly says 'I don't know', 'não sei', wants to skip"
        ),
    )


# Decision-making tools (separate from message generation)


class SelectFlowEdge(BaseModel):
    """Select which edge/path to take in the flow based on context."""

    selected_edge_index: int | None = Field(
        default=None,
        description="Index of the selected edge (0-based), or null if no edge applies",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence level in edge selection (0-1)",
    )
    reasoning: str | None = Field(
        default=None,
        description="Brief explanation of why this edge was selected",
    )


class SelectNextQuestion(BaseModel):
    """Select which question to ask next from available options."""

    selected_question_index: int | None = Field(
        default=None,
        description="Index of the selected question (0-based), or null if no question applies",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence level in question selection (0-1)",
    )
    reasoning: str | None = Field(
        default=None,
        description="Brief explanation of why this question was selected",
    )


# Decision-making tool registry
DECISION_TOOLS = [
    SelectFlowEdge,
    SelectNextQuestion,
]
