"""Internal tools for flow engine decision-making.

These tools are used internally by the engine for routing and decision logic,
not exposed to users through the responder.
"""


from pydantic import BaseModel, Field


class SelectFlowEdge(BaseModel):
    """Select which edge/path to take in the flow based on context."""

    selected_edge_index: int | None = Field(
        default=None,
        description="Index of the selected edge (0-based), or null if no edge applies",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
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
        ge=0.0,
        le=1.0,
        description="Confidence level in question selection (0-1)",
    )
    reasoning: str | None = Field(
        default=None,
        description="Brief explanation of why this question was selected",
    )
