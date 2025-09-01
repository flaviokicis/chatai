"""
Public tenant API endpoints (no authentication required).
These are for user-facing pages that need to display tenant/flow information.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.repository import get_active_tenants, get_flows_by_tenant
from app.db.session import get_db_session

router = APIRouter(prefix="/tenants", tags=["public_tenants"])


class PublicTenantResponse(BaseModel):
    """Public tenant info (no sensitive data)."""
    id: UUID
    name: str  # Could be derived from owner name or business name
    description: str | None = None


class PublicFlowResponse(BaseModel):
    """Public flow info (no sensitive definition data)."""
    id: UUID
    name: str
    flow_id: str
    description: str | None = None


@router.get("", response_model=list[PublicTenantResponse])
async def list_public_tenants(
    session: Session = Depends(get_db_session)
) -> list[PublicTenantResponse]:
    """List tenants (public info only, no auth required)."""
    tenants = get_active_tenants(session)
    return [
        PublicTenantResponse(
            id=tenant.id,
            name=f"{tenant.owner_first_name} {tenant.owner_last_name}",
            description=tenant.project_config.project_description if tenant.project_config else None,
        )
        for tenant in tenants
    ]


@router.get("/{tenant_id}/flows", response_model=list[PublicFlowResponse])
async def list_public_tenant_flows(
    tenant_id: UUID,
    session: Session = Depends(get_db_session)
) -> list[PublicFlowResponse]:
    """List flows for a tenant (public info only, no auth required)."""
    flows = get_flows_by_tenant(session, tenant_id)
    return [
        PublicFlowResponse(
            id=flow.id,
            name=flow.name,
            flow_id=flow.flow_id,
            description=None,  # Could extract from flow metadata if needed
        )
        for flow in flows
    ]


