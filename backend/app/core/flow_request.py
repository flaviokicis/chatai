"""Flow processing request model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FlowRequest:
    """Request for flow processing."""
    
    user_id: str
    user_message: str
    flow_definition: dict[str, Any]
    flow_metadata: dict[str, Any]
    tenant_id: str
    project_context: Any | None = None
    channel_id: str | None = None
