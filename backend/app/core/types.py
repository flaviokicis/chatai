"""
Common type definitions for the core module.

This module defines type aliases and TypedDicts that are MISSING from
other parts of the codebase. It imports existing types rather than
duplicating them.
"""

from typing import Any, NotRequired, Required, TypeAlias, TypedDict
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


class RequestFlowMetadata(TypedDict):
    """Typed structure for flow metadata in requests.

    This is different from FlowMetadata in ir.py which is for flow definitions.
    This is for the metadata that comes with flow processing requests.

    Critical fields are Required, others are NotRequired for flexibility.
    """

    # These fields MUST be present - FlowProcessor depends on them
    selected_flow_id: Required[str]  # Used by FlowProcessor to set context.flow_id
    flow_id: Required[str]  # Primary flow identifier

    # These fields are optional
    flow_name: NotRequired[str]
    flow_definition: NotRequired[dict[str, Any]]
    tenant_id: NotRequired[str]
    channel_id: NotRequired[str]
    thread_id: NotRequired[str]  # Added for WhatsApp CLI support


# Type Guards for runtime validation
from typing import TypeGuard


def is_flow_state(data: Any) -> TypeGuard[FlowState]:
    """
    Runtime validation for flow state structure.

    Use this to validate data loaded from storage before using it.
    """
    return (
        isinstance(data, dict)
        and "answers" in data
        and isinstance(data.get("answers"), dict)
        and "pending_field" in data
        and "is_complete" in data
        and isinstance(data.get("is_complete"), bool)
    )


def is_request_flow_metadata(data: Any) -> TypeGuard[RequestFlowMetadata]:
    """
    Runtime validation for flow metadata structure.

    Use this to validate metadata from requests.
    """
    return (
        isinstance(data, dict)
        and "flow_id" in data
        and "selected_flow_id" in data  # Both are now required
    )


def validate_flow_metadata(data: dict[str, Any]) -> RequestFlowMetadata:
    """Validate flow metadata with helpful error messages.

    Args:
        data: Dictionary to validate

    Returns:
        Validated RequestFlowMetadata

    Raises:
        ValueError: If required fields are missing or invalid
    """
    # Check required fields
    required_fields = ["selected_flow_id", "flow_id"]
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        raise ValueError(
            f"Missing required fields in flow_metadata: {missing_fields}. "
            f"Provided fields: {list(data.keys())}"
        )

    # Check for empty strings (the bug we actually had)
    if not data["selected_flow_id"]:
        raise ValueError("selected_flow_id cannot be an empty string")

    if not data["flow_id"]:
        raise ValueError("flow_id cannot be an empty string")

    return data  # type: ignore[return-value]


def is_whatsapp_message(data: Any) -> TypeGuard[WhatsAppMessage]:
    """
    Runtime validation for WhatsApp message structure.
    """
    return (
        isinstance(data, dict)
        and "text" in data
        and isinstance(data.get("text"), str)
        and "delay_ms" in data
        and isinstance(data.get("delay_ms"), int)
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
            is_complete=bool(data.get("is_complete", False)),
        )

    return None
