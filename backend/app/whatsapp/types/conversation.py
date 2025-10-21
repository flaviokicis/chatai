from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeGuard
from uuid import UUID

if TYPE_CHECKING:
    from app.services.tenant_config_service import ProjectContext


@dataclass(frozen=True, slots=True)
class ConversationSetup:
    tenant_id: UUID
    channel_instance_id: UUID
    thread_id: UUID
    contact_id: UUID
    flow_id: str
    flow_name: str
    selected_flow_id: str
    flow_definition: dict[str, object]
    project_context: ProjectContext


def is_conversation_setup(data: Any) -> TypeGuard[ConversationSetup]:
    """Runtime type guard for ConversationSetup.
    
    Use to validate data coming from database operations.
    """
    return isinstance(data, ConversationSetup)

