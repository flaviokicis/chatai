"""Typed metadata objects for messages to improve type safety.

This module provides typed alternatives to raw dictionaries for message metadata,
enabling better IDE support, validation, and maintainability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class MessageMetadata:
    """Base metadata for messages with common fields."""
    
    # Tracing and correlation
    correlation_id: str | None = None
    trace_id: str | None = None
    
    # Timing information
    processing_started_at: float | None = None
    processing_completed_at: float | None = None
    
    # Source information
    source_system: str | None = None
    source_version: str | None = None
    
    # Additional untyped data for flexibility
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InboundMessageMetadata(MessageMetadata):
    """Metadata specific to inbound messages."""
    
    # Channel-specific information
    provider_message_id: str | None = None
    channel_type: str | None = None
    channel_instance_id: UUID | None = None
    
    # Message context
    is_reply_to: str | None = None
    thread_id: UUID | None = None
    contact_id: UUID | None = None
    
    # Processing flags
    requires_human_review: bool = False
    priority: str = "normal"  # low, normal, high, urgent
    
    # Content analysis
    detected_language: str | None = None
    content_type: str = "text"  # text, audio, image, document, etc.
    
    # Rate limiting
    user_message_count: int = 0
    rate_limit_remaining: int | None = None


@dataclass(slots=True)
class OutboundMessageMetadata(MessageMetadata):
    """Metadata specific to outbound messages."""
    
    # Delivery tracking
    delivery_status: str = "pending"  # pending, sent, delivered, read, failed
    delivery_attempts: int = 0
    max_delivery_attempts: int = 3
    
    # Message characteristics
    message_type: str = "response"  # response, notification, broadcast, etc.
    urgency: str = "normal"  # low, normal, high
    
    # Flow context
    flow_id: UUID | None = None
    flow_node_id: str | None = None
    flow_step_name: str | None = None
    
    # Response generation
    generated_by: str | None = None  # llm, template, rule-based
    generation_model: str | None = None
    generation_confidence: float | None = None
    
    # Personalization
    personalized: bool = False
    personalization_context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentResultMetadata(MessageMetadata):
    """Metadata for agent processing results."""
    
    # Agent information
    agent_type: str | None = None
    agent_version: str | None = None
    agent_instance_id: str | None = None
    
    # Processing details
    processing_duration_ms: float | None = None
    llm_calls_made: int = 0
    tokens_consumed: int = 0
    
    # Decision tracking
    decision_path: list[str] = field(default_factory=list)
    confidence_score: float | None = None
    
    # State changes
    state_mutations: list[str] = field(default_factory=list)
    
    # Error handling
    errors_encountered: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    # Handoff context
    handoff_reason: str | None = None
    handoff_urgency: str | None = None
    handoff_context: dict[str, Any] = field(default_factory=dict)


