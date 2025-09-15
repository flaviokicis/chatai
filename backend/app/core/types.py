"""
Common type definitions for the core module.

This module defines type aliases and TypedDicts that are MISSING from
other parts of the codebase. It imports existing types rather than
duplicating them.
"""

from typing import TypeAlias, TypedDict, Any
from uuid import UUID

# Import existing types instead of duplicating
from app.flow_core.flow_types import (
    FlowState,  # Already defined
    WhatsAppMessage,  # Already defined for messages
)

# Type Aliases for clarity and consistency (these don't exist elsewhere)
UserId: TypeAlias = str
AgentType: TypeAlias = str  
SessionId: TypeAlias = str
ThreadId: TypeAlias = UUID
TenantId: TypeAlias = UUID
ChannelId: TypeAlias = UUID
FlowId: TypeAlias = str


class EventDict(TypedDict):
    """Typed structure for events (currently untyped 'dict' in ConversationStore)."""
    timestamp: float
    type: str
    user_id: str
    data: dict[str, Any]


class RequestFlowMetadata(TypedDict, total=False):
    """Typed structure for flow metadata in requests.
    
    This is different from FlowMetadata in ir.py which is for flow definitions.
    This is for the metadata that comes with flow processing requests.
    """
    flow_id: str
    flow_name: str
    selected_flow_id: str
    flow_definition: dict[str, Any]
    tenant_id: str
    channel_id: str


# Type Guards for runtime validation
from typing import TypeGuard


def is_flow_state(data: Any) -> TypeGuard[FlowState]:
    """
    Runtime validation for flow state structure.
    
    Use this to validate data loaded from storage before using it.
    """
    return (
        isinstance(data, dict) and
        "answers" in data and
        isinstance(data.get("answers"), dict) and
        "pending_field" in data and
        "is_complete" in data and
        isinstance(data.get("is_complete"), bool)
    )


def is_request_flow_metadata(data: Any) -> TypeGuard[RequestFlowMetadata]:
    """
    Runtime validation for flow metadata structure.
    
    Use this to validate metadata from requests.
    """
    return (
        isinstance(data, dict) and
        ("flow_id" in data or "selected_flow_id" in data)
    )


def is_whatsapp_message(data: Any) -> TypeGuard[WhatsAppMessage]:
    """
    Runtime validation for WhatsApp message structure.
    """
    return (
        isinstance(data, dict) and
        "text" in data and
        isinstance(data.get("text"), str) and
        "delay_ms" in data and
        isinstance(data.get("delay_ms"), int)
    )


def validate_and_cast_flow_state(data: Any) -> FlowState | None:
    """
    Validate and safely cast data to FlowState.
    
    Returns None if validation fails, preventing runtime errors.
    """
    if is_flow_state(data):
        return data
    
    # Try to construct valid state from partial data
    if isinstance(data, dict):
        return FlowState(
            answers=data.get("answers", {}),
            pending_field=data.get("pending_field"),
            active_path=data.get("active_path"),
            clarification_count=data.get("clarification_count", 0),
            path_corrections=data.get("path_corrections", 0),
            is_complete=bool(data.get("is_complete", False))
        )
    
    return None
