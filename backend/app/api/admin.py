"""
Admin API endpoints for tenant and database management.

Requires ADMIN_PASSWORD environment variable for authentication.
Provides CRUD operations for tenants, channels, and flows with proper cascade deletes.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Generator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import ChannelType
from app.db.repository import (
    create_channel_instance,
    create_flow,
    create_tenant_with_config,
    delete_tenant_cascade,
    get_active_tenants,
    get_channel_instances_by_tenant,
    get_flow_by_id,
    get_flows_by_tenant,
    get_tenant_by_id,
    update_flow_definition,
    update_tenant,
)
from app.db.session import create_session

router = APIRouter(prefix="/controller", tags=["controller"])
security = HTTPBearer()


# Pydantic models for API
class AdminLoginRequest(BaseModel):
    password: str


class AdminLoginResponse(BaseModel):
    success: bool
    message: str
    expires_at: datetime | None = None


class TenantCreateRequest(BaseModel):
    owner_first_name: str = Field(..., min_length=1, max_length=120)
    owner_last_name: str = Field(..., min_length=1, max_length=120)
    owner_email: str = Field(..., min_length=1)
    project_description: str | None = None
    target_audience: str | None = None
    communication_style: str | None = None


class TenantUpdateRequest(BaseModel):
    owner_first_name: str | None = Field(None, min_length=1, max_length=120)
    owner_last_name: str | None = Field(None, min_length=1, max_length=120)
    owner_email: str | None = Field(None, min_length=1)
    project_description: str | None = None
    target_audience: str | None = None
    communication_style: str | None = None


class ChannelCreateRequest(BaseModel):
    channel_type: ChannelType
    identifier: str = Field(..., min_length=1)
    phone_number: str | None = None
    extra: Dict[str, Any] | None = None


class FlowUpdateRequest(BaseModel):
    definition: Dict[str, Any]


class TenantResponse(BaseModel):
    id: UUID
    owner_first_name: str
    owner_last_name: str
    owner_email: str
    created_at: datetime
    updated_at: datetime
    project_description: str | None = None
    target_audience: str | None = None
    communication_style: str | None = None
    channel_count: int
    flow_count: int


class ChannelResponse(BaseModel):
    id: UUID
    channel_type: ChannelType
    identifier: str
    phone_number: str | None
    extra: dict[str, Any] | None
    created_at: datetime


class FlowResponse(BaseModel):
    id: UUID
    name: str
    flow_id: str
    definition: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


# Authentication helpers
def get_admin_password() -> str:
    """Get admin password from environment."""
    password = os.getenv("ADMIN_PASSWORD")
    if not password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin password not configured. Set ADMIN_PASSWORD environment variable."
        )
    return password


def verify_admin_session(request: Request) -> bool:
    """Verify admin session is valid."""
    session = request.session
    is_admin = session.get("is_admin", False)
    expires_at = session.get("admin_expires_at")
    
    if not is_admin or not expires_at:
        return False
    
    try:
        expire_time = datetime.fromisoformat(expires_at)
        return datetime.now() < expire_time
    except (ValueError, TypeError):
        return False


def require_admin_auth(request: Request) -> None:
    """Dependency to require admin authentication."""
    if not verify_admin_session(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required"
        )


def get_db() -> Generator[Session, None, None]:
    """Database session dependency."""
    session = create_session()
    try:
        yield session
    finally:
        session.close()


# API endpoints
@router.post("/auth", response_model=AdminLoginResponse)
async def admin_login(request: Request, login_req: AdminLoginRequest) -> AdminLoginResponse:
    """Authenticate admin user with password."""
    try:
        admin_password = get_admin_password()
    except HTTPException:
        return AdminLoginResponse(success=False, message="Admin authentication not configured")
    
    if login_req.password != admin_password:
        return AdminLoginResponse(success=False, message="Invalid password")
    
    # Set session with 24 hour expiry
    expires_at = datetime.now() + timedelta(hours=24)
    request.session["is_admin"] = True
    request.session["admin_expires_at"] = expires_at.isoformat()
    
    return AdminLoginResponse(
        success=True,
        message="Authentication successful",
        expires_at=expires_at
    )


@router.post("/logout")
async def admin_logout(request: Request) -> dict[str, str]:
    """Logout admin user."""
    request.session.clear()
    return {"message": "Logged out successfully"}


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    request: Request,
    db: Session = Depends(get_db)
) -> list[TenantResponse]:
    """List all tenants with summary information."""
    require_admin_auth(request)
    
    tenants = get_active_tenants(db)
    result = []
    
    for tenant in tenants:
        channels = get_channel_instances_by_tenant(db, tenant.id)
        flows = get_flows_by_tenant(db, tenant.id)
        
        result.append(TenantResponse(
            id=tenant.id,
            owner_first_name=tenant.owner_first_name,
            owner_last_name=tenant.owner_last_name,
            owner_email=tenant.owner_email,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            project_description=tenant.project_config.project_description if tenant.project_config else None,
            target_audience=tenant.project_config.target_audience if tenant.project_config else None,
            communication_style=tenant.project_config.communication_style if tenant.project_config else None,
            channel_count=len(channels),
            flow_count=len(flows)
        ))
    
    return result


@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(
    request: Request,
    tenant_req: TenantCreateRequest,
    db: Session = Depends(get_db)
) -> TenantResponse:
    """Create a new tenant."""
    require_admin_auth(request)
    
    try:
        tenant = create_tenant_with_config(
            db,
            first_name=tenant_req.owner_first_name,
            last_name=tenant_req.owner_last_name,
            email=tenant_req.owner_email,
            project_description=tenant_req.project_description,
            target_audience=tenant_req.target_audience,
            communication_style=tenant_req.communication_style
        )
        db.commit()
        
        return TenantResponse(
            id=tenant.id,
            owner_first_name=tenant.owner_first_name,
            owner_last_name=tenant.owner_last_name,
            owner_email=tenant.owner_email,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            project_description=tenant.project_config.project_description if tenant.project_config else None,
            target_audience=tenant.project_config.target_audience if tenant.project_config else None,
            communication_style=tenant.project_config.communication_style if tenant.project_config else None,
            channel_count=0,
            flow_count=0
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Invalid data: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant_endpoint(
    request: Request,
    tenant_id: UUID,
    tenant_req: TenantUpdateRequest,
    db: Session = Depends(get_db)
) -> TenantResponse:
    """Update a tenant."""
    require_admin_auth(request)
    
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    try:
        updated_tenant = update_tenant(
            db,
            tenant_id=tenant_id,
            first_name=tenant_req.owner_first_name,
            last_name=tenant_req.owner_last_name,
            email=tenant_req.owner_email,
            project_description=tenant_req.project_description,
            target_audience=tenant_req.target_audience,
            communication_style=tenant_req.communication_style
        )
        db.commit()
        
        channels = get_channel_instances_by_tenant(db, tenant_id)
        flows = get_flows_by_tenant(db, tenant_id)
        
        return TenantResponse(
            id=updated_tenant.id,
            owner_first_name=updated_tenant.owner_first_name,
            owner_last_name=updated_tenant.owner_last_name,
            owner_email=updated_tenant.owner_email,
            created_at=updated_tenant.created_at,
            updated_at=updated_tenant.updated_at,
            project_description=updated_tenant.project_config.project_description if updated_tenant.project_config else None,
            target_audience=updated_tenant.project_config.target_audience if updated_tenant.project_config else None,
            communication_style=updated_tenant.project_config.communication_style if updated_tenant.project_config else None,
            channel_count=len(channels),
            flow_count=len(flows)
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/tenants/{tenant_id}")
async def delete_tenant_endpoint(
    request: Request,
    tenant_id: UUID,
    db: Session = Depends(get_db)
) -> dict[str, str]:
    """Delete a tenant and all associated data (cascading)."""
    require_admin_auth(request)
    
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    try:
        delete_tenant_cascade(db, tenant_id)
        db.commit()
        return {"message": f"Tenant {tenant_id} and all associated data deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tenants/{tenant_id}/channels", response_model=list[ChannelResponse])
async def list_tenant_channels(
    request: Request,
    tenant_id: UUID,
    db: Session = Depends(get_db)
) -> list[ChannelResponse]:
    """List channels for a tenant."""
    require_admin_auth(request)
    
    channels = get_channel_instances_by_tenant(db, tenant_id)
    return [
        ChannelResponse(
            id=channel.id,
            channel_type=channel.channel_type,
            identifier=channel.identifier,
            phone_number=channel.phone_number,
            extra=channel.extra,
            created_at=channel.created_at
        )
        for channel in channels
    ]


@router.post("/tenants/{tenant_id}/channels", response_model=ChannelResponse)
async def create_tenant_channel(
    request: Request,
    tenant_id: UUID,
    channel_req: ChannelCreateRequest,
    db: Session = Depends(get_db)
) -> ChannelResponse:
    """Create a new channel for a tenant."""
    require_admin_auth(request)
    
    # Verify tenant exists
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    try:
        channel = create_channel_instance(
            db,
            tenant_id=tenant_id,
            channel_type=channel_req.channel_type,
            identifier=channel_req.identifier,
            phone_number=channel_req.phone_number,
            extra=channel_req.extra
        )
        db.commit()
        
        return ChannelResponse(
            id=channel.id,
            channel_type=channel.channel_type,
            identifier=channel.identifier,
            phone_number=channel.phone_number,
            extra=channel.extra,
            created_at=channel.created_at
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tenants/{tenant_id}/flows", response_model=list[FlowResponse])
async def list_tenant_flows(
    request: Request,
    tenant_id: UUID,
    db: Session = Depends(get_db)
) -> list[FlowResponse]:
    """List flows for a tenant."""
    require_admin_auth(request)
    
    flows = get_flows_by_tenant(db, tenant_id)
    return [
        FlowResponse(
            id=flow.id,
            name=flow.name,
            flow_id=flow.flow_id,
            definition=flow.definition,
            created_at=flow.created_at,
            updated_at=flow.updated_at
        )
        for flow in flows
    ]


@router.put("/flows/{flow_id}", response_model=FlowResponse)
async def update_flow_endpoint(
    request: Request,
    flow_id: UUID,
    flow_req: FlowUpdateRequest,
    db: Session = Depends(get_db)
) -> FlowResponse:
    """Update a flow's definition (JSON editor)."""
    require_admin_auth(request)
    
    flow = get_flow_by_id(db, flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    try:
        updated_flow = update_flow_definition(db, flow_id, flow_req.definition)
        db.commit()
        
        return FlowResponse(
            id=updated_flow.id,
            name=updated_flow.name,
            flow_id=updated_flow.flow_id,
            definition=updated_flow.definition,
            created_at=updated_flow.created_at,
            updated_at=updated_flow.updated_at
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health")
async def admin_health() -> dict[str, str]:
    """Health check for admin API."""
    return {"status": "healthy", "service": "controller"}