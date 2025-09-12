"""Additional typed objects for handoff-related data structures.

This module provides typed alternatives to raw dictionaries used in handoff processing,
complementing the existing HandoffData class with additional structured types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class HandoffReason(BaseModel):
    """Structured reason for handoff with categorization."""

    category: Literal[
        "user_request",
        "escalation",
        "technical_issue",
        "complex_query",
        "out_of_scope",
        "error_recovery",
        "timeout",
        "other"
    ] = Field(description="Category of handoff reason")

    description: str = Field(description="Human-readable description")
    technical_details: str | None = Field(default=None, description="Technical details for debugging")
    severity: Literal["low", "medium", "high", "critical"] = Field(
        default="medium", description="Severity level"
    )

    # Context information
    triggered_by_node: str | None = Field(default=None, description="Flow node that triggered handoff")
    user_input: str | None = Field(default=None, description="User input that caused handoff")
    error_code: str | None = Field(default=None, description="Error code if applicable")

    @property
    def is_error_related(self) -> bool:
        """Check if handoff is due to an error."""
        return self.category in {"technical_issue", "error_recovery", "timeout"}

    @property
    def requires_immediate_attention(self) -> bool:
        """Check if handoff requires immediate attention."""
        return self.severity in {"high", "critical"}


class HandoffContext(BaseModel):
    """Rich context information for handoff requests."""

    # Flow state
    flow_progress: dict[str, Any] = Field(default_factory=dict, description="Current flow progress")
    completed_steps: list[str] = Field(default_factory=list, description="Completed flow steps")
    pending_validations: list[str] = Field(default_factory=list, description="Pending validations")

    # User interaction history
    interaction_count: int = Field(default=0, description="Number of user interactions")
    last_user_message: str | None = Field(default=None, description="Last user message")
    user_sentiment: Literal["positive", "neutral", "negative", "frustrated"] | None = Field(
        default=None, description="Detected user sentiment"
    )

    # Technical context
    session_duration_minutes: float | None = Field(default=None, description="Session duration")
    errors_encountered: list[str] = Field(default_factory=list, description="Errors during session")
    retry_attempts: int = Field(default=0, description="Number of retry attempts")

    # Business context
    customer_tier: str | None = Field(default=None, description="Customer tier/priority")
    account_status: str | None = Field(default=None, description="Account status")
    previous_interactions: int = Field(default=0, description="Previous interaction count")

    # Agent preferences
    preferred_language: str | None = Field(default=None, description="User's preferred language")
    accessibility_needs: list[str] = Field(default_factory=list, description="Accessibility requirements")
    communication_style: str | None = Field(default=None, description="Preferred communication style")


@dataclass(slots=True)
class HandoffResolution:
    """Information about how a handoff was resolved."""

    # Resolution identification
    handoff_id: UUID
    resolved_by: str  # agent_id, system, etc.
    resolved_at: datetime = field(default_factory=datetime.utcnow)

    # Resolution details
    resolution_type: str = "completed"  # completed, transferred, escalated, cancelled
    resolution_summary: str | None = None
    resolution_notes: str | None = None

    # Outcome
    customer_satisfied: bool | None = None
    issue_resolved: bool = True
    follow_up_required: bool = False
    follow_up_date: datetime | None = None

    # Metrics
    resolution_time_minutes: float | None = None
    agent_effort_score: int | None = None  # 1-5 scale
    complexity_score: int | None = None  # 1-5 scale

    # Additional context
    resolution_context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HandoffMetrics:
    """Metrics and analytics for handoff performance."""

    # Volume metrics
    total_handoffs: int = 0
    handoffs_by_category: dict[str, int] = field(default_factory=dict)
    handoffs_by_severity: dict[str, int] = field(default_factory=dict)

    # Timing metrics
    average_resolution_time_minutes: float = 0.0
    median_resolution_time_minutes: float = 0.0
    max_resolution_time_minutes: float = 0.0

    # Success metrics
    resolution_rate: float = 0.0  # 0.0 to 1.0
    customer_satisfaction_rate: float = 0.0  # 0.0 to 1.0
    first_contact_resolution_rate: float = 0.0  # 0.0 to 1.0

    # Quality metrics
    average_agent_effort_score: float = 0.0
    average_complexity_score: float = 0.0

    # Trend data
    handoff_trend: Literal["increasing", "stable", "decreasing"] = "stable"
    trend_period_days: int = 30

    # Time period
    period_start: datetime | None = None
    period_end: datetime | None = None

    def add_handoff_resolution(self, resolution: HandoffResolution, reason: HandoffReason) -> None:
        """Update metrics with a new handoff resolution."""
        self.total_handoffs += 1

        # Update category counts
        if reason.category not in self.handoffs_by_category:
            self.handoffs_by_category[reason.category] = 0
        self.handoffs_by_category[reason.category] += 1

        # Update severity counts
        if reason.severity not in self.handoffs_by_severity:
            self.handoffs_by_severity[reason.severity] = 0
        self.handoffs_by_severity[reason.severity] += 1

        # Update resolution metrics (simplified - real implementation would track all resolutions)
        if resolution.resolution_time_minutes:
            # This is a simplified update - real implementation would maintain running averages
            if self.average_resolution_time_minutes == 0:
                self.average_resolution_time_minutes = resolution.resolution_time_minutes
            else:
                self.average_resolution_time_minutes = (
                    self.average_resolution_time_minutes + resolution.resolution_time_minutes
                ) / 2


class HandoffQueue(BaseModel):
    """Representation of a handoff queue with priority and routing."""

    queue_id: str = Field(description="Unique queue identifier")
    queue_name: str = Field(description="Human-readable queue name")
    queue_type: Literal["general", "technical", "sales", "billing", "vip"] = Field(
        description="Queue type for routing"
    )

    # Queue configuration
    max_capacity: int = Field(default=100, description="Maximum queue capacity")
    priority_levels: list[str] = Field(
        default_factory=lambda: ["low", "medium", "high", "critical"],
        description="Supported priority levels"
    )

    # Current state
    current_size: int = Field(default=0, description="Current number of items in queue")
    average_wait_time_minutes: float = Field(default=0.0, description="Average wait time")

    # Agent availability
    available_agents: int = Field(default=0, description="Number of available agents")
    total_agents: int = Field(default=0, description="Total agents assigned to queue")

    # Queue rules
    auto_escalation_minutes: int = Field(default=60, description="Auto-escalation timeout")
    requires_skills: list[str] = Field(default_factory=list, description="Required agent skills")
    business_hours_only: bool = Field(default=True, description="Only process during business hours")

    @property
    def is_at_capacity(self) -> bool:
        """Check if queue is at maximum capacity."""
        return self.current_size >= self.max_capacity

    @property
    def agent_utilization(self) -> float:
        """Calculate agent utilization rate."""
        if self.total_agents == 0:
            return 0.0
        return (self.total_agents - self.available_agents) / self.total_agents

    @property
    def estimated_wait_minutes(self) -> float:
        """Estimate wait time for new handoffs."""
        if self.available_agents > 0:
            return 0.0
        return self.average_wait_time_minutes * (self.current_size / max(self.total_agents, 1))


@dataclass(slots=True)
class HandoffRoutingDecision:
    """Decision about where to route a handoff."""

    # Routing decision
    target_queue: str
    priority: str = "medium"
    estimated_wait_minutes: float = 0.0

    # Decision reasoning
    routing_reason: str | None = None
    confidence_score: float = 1.0  # 0.0 to 1.0

    # Alternative options
    alternative_queues: list[str] = field(default_factory=list)

    # Special handling
    requires_escalation: bool = False
    requires_specialist: bool = False
    specialist_skills: list[str] = field(default_factory=list)

    # Timing
    decision_made_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        """Check if routing decision has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_high_confidence(self) -> bool:
        """Check if routing decision has high confidence."""
        return self.confidence_score >= 0.8


def create_handoff_reason(
    category: str,
    description: str,
    severity: str = "medium",
    technical_details: str | None = None,
    triggered_by_node: str | None = None,
    user_input: str | None = None,
    error_code: str | None = None,
) -> HandoffReason:
    """Helper function to create a structured handoff reason."""
    return HandoffReason(
        category=category,  # type: ignore[arg-type]
        description=description,
        severity=severity,  # type: ignore[arg-type]
        technical_details=technical_details,
        triggered_by_node=triggered_by_node,
        user_input=user_input,
        error_code=error_code,
    )


def create_handoff_context(
    collected_answers: dict[str, Any] | None = None,
    interaction_count: int = 0,
    last_user_message: str | None = None,
    session_duration_minutes: float | None = None,
    errors_encountered: list[str] | None = None,
    **kwargs: Any,
) -> HandoffContext:
    """Helper function to create handoff context from flow state."""
    return HandoffContext(
        flow_progress=collected_answers or {},
        interaction_count=interaction_count,
        last_user_message=last_user_message,
        session_duration_minutes=session_duration_minutes,
        errors_encountered=errors_encountered or [],
        **kwargs,
    )
