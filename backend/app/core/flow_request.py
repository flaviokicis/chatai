"""Flow processing request model."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.types import RequestFlowMetadata
from app.services.tenant_config_service import ProjectContext


@dataclass(frozen=True, slots=True)
class FlowRequest:
    user_id: str
    user_message: str
    flow_definition: dict[str, object] | None
    flow_metadata: RequestFlowMetadata
    tenant_id: UUID
    project_context: ProjectContext | None = None
    channel_id: str | None = None
