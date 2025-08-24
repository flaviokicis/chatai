from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import ChannelType
from app.db.session import get_db_session
from app.services.tenant_service import (
    DuplicateChannelError,
    TenantNotFoundError,
    TenantService,
    TenantServiceError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateTenantRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)

    project_description: str | None = Field(default=None, max_length=50_000)
    target_audience: str | None = Field(default=None, max_length=50_000)
    communication_style: str | None = Field(default=None, max_length=50_000)


class TenantResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str


class TenantWithConfigResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str
    project_description: str | None = None
    target_audience: str | None = None
    communication_style: str | None = None


class UpdateTenantConfigRequest(BaseModel):
    project_description: str | None = Field(default=None, max_length=50_000)
    target_audience: str | None = Field(default=None, max_length=50_000)
    communication_style: str | None = Field(default=None, max_length=50_000)


@router.post("/tenants", response_model=TenantResponse)
def create_tenant(
    payload: CreateTenantRequest, session: Session = Depends(get_db_session)
) -> TenantResponse:
    """Create a new tenant with project configuration."""
    service = TenantService(session)
    try:
        tenant = service.create_tenant(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            project_description=payload.project_description,
            target_audience=payload.target_audience,
            communication_style=payload.communication_style,
        )
        return TenantResponse(
            id=tenant.id,
            first_name=tenant.owner_first_name,
            last_name=tenant.owner_last_name,
            email=tenant.owner_email,
        )
    except TenantServiceError as exc:
        logger.error("Failed to create tenant: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class CreateChannelInstanceRequest(BaseModel):
    channel_type: ChannelType
    identifier: str = Field(description="e.g., whatsapp:+14155238886")
    phone_number: str | None = None
    extra: dict | None = None


class ChannelInstanceResponse(BaseModel):
    id: UUID
    channel_type: ChannelType
    identifier: str
    phone_number: str | None


@router.post("/tenants/{tenant_id}/channels", response_model=ChannelInstanceResponse)
def create_channel_instance(
    payload: CreateChannelInstanceRequest,
    tenant_id: UUID = Path(...),
    session: Session = Depends(get_db_session),
) -> ChannelInstanceResponse:
    """Create a new channel instance for a tenant."""
    service = TenantService(session)
    try:
        channel = service.create_channel_instance(
            tenant_id=tenant_id,
            channel_type=payload.channel_type,
            identifier=payload.identifier,
            phone_number=payload.phone_number,
            extra=payload.extra,
        )
        return ChannelInstanceResponse(
            id=channel.id,
            channel_type=channel.channel_type,
            identifier=channel.identifier,
            phone_number=channel.phone_number,
        )
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateChannelError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TenantServiceError as exc:
        logger.error("Failed to create channel instance: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class CreateFlowRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    flow_id: str = Field(min_length=1, max_length=200)
    channel_instance_id: UUID
    definition: dict


class UpdateFlowRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    definition: Optional[dict] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)


class FlowResponse(BaseModel):
    id: UUID
    name: str
    flow_id: str
    channel_instance_id: UUID


@router.post("/tenants/{tenant_id}/flows", response_model=FlowResponse)
def create_flow(
    payload: CreateFlowRequest,
    tenant_id: UUID = Path(...),
    session=Depends(get_db_session),
) -> Any:
    service = TenantService(session)
    try:
        f = service.create_flow(
            tenant_id=tenant_id,
            channel_instance_id=payload.channel_instance_id,
            name=payload.name,
            flow_id=payload.flow_id,
            definition=payload.definition,
        )
        return FlowResponse(
            id=f.id,
            name=f.name,
            flow_id=f.flow_id,
            channel_instance_id=f.channel_instance_id,
        )
    except TenantServiceError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Failed to create flow: {exc}")


@router.put("/tenants/{tenant_id}/flows/{flow_id}", response_model=FlowResponse)
def update_flow(
    payload: UpdateFlowRequest,
    tenant_id: UUID = Path(...),
    flow_id: UUID = Path(...),
    session: Session = Depends(get_db_session),
) -> FlowResponse:
    """Update an existing flow."""
    service = TenantService(session)
    try:
        flow = service.update_flow(
            tenant_id=tenant_id,
            flow_id=flow_id,
            name=payload.name,
            definition=payload.definition,
            is_active=payload.is_active,
        )
        return FlowResponse(
            id=flow.id,
            name=flow.name,
            flow_id=flow.flow_id,
            channel_instance_id=flow.channel_instance_id,
        )
    except TenantServiceError as exc:
        logger.error("Failed to update flow: %s", exc)
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=f"Failed to update flow: {exc}") from exc


@router.get("/tenants", response_model=list[TenantResponse])
def list_tenants(session: Session = Depends(get_db_session)) -> list[TenantResponse]:
    """List all active tenants."""
    service = TenantService(session)
    tenants = service.get_all_tenants()
    return [
        TenantResponse(
            id=t.id,
            first_name=t.owner_first_name,
            last_name=t.owner_last_name,
            email=t.owner_email,
        )
        for t in tenants
    ]


@router.get("/tenants/{tenant_id}", response_model=TenantWithConfigResponse)
def get_tenant(
    tenant_id: UUID = Path(...), session: Session = Depends(get_db_session)
) -> TenantWithConfigResponse:
    """Get a specific tenant with project configuration."""
    service = TenantService(session)
    try:
        tenant = service.get_tenant_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")

        return TenantWithConfigResponse(
            id=tenant.id,
            first_name=tenant.owner_first_name,
            last_name=tenant.owner_last_name,
            email=tenant.owner_email,
            project_description=tenant.project_config.project_description
            if tenant.project_config
            else None,
            target_audience=tenant.project_config.target_audience
            if tenant.project_config
            else None,
            communication_style=tenant.project_config.communication_style
            if tenant.project_config
            else None,
        )
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TenantServiceError as exc:
        logger.error("Failed to get tenant: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/tenants/{tenant_id}/config", response_model=TenantWithConfigResponse)
def update_tenant_config(
    payload: UpdateTenantConfigRequest,
    tenant_id: UUID = Path(...),
    session: Session = Depends(get_db_session),
) -> TenantWithConfigResponse:
    """Update tenant project configuration."""
    service = TenantService(session)
    try:
        tenant = service.update_tenant_config(
            tenant_id=tenant_id,
            project_description=payload.project_description,
            target_audience=payload.target_audience,
            communication_style=payload.communication_style,
        )
        return TenantWithConfigResponse(
            id=tenant.id,
            first_name=tenant.owner_first_name,
            last_name=tenant.owner_last_name,
            email=tenant.owner_email,
            project_description=tenant.project_config.project_description
            if tenant.project_config
            else None,
            target_audience=tenant.project_config.target_audience
            if tenant.project_config
            else None,
            communication_style=tenant.project_config.communication_style
            if tenant.project_config
            else None,
        )
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TenantServiceError as exc:
        logger.error("Failed to update tenant config: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tenants/{tenant_id}/channels", response_model=list[ChannelInstanceResponse])
def list_channel_instances(
    tenant_id: UUID = Path(...), session: Session = Depends(get_db_session)
) -> list[ChannelInstanceResponse]:
    """List all channel instances for a tenant."""
    service = TenantService(session)
    try:
        channels = service.get_channel_instances(tenant_id)
        return [
            ChannelInstanceResponse(
                id=ch.id,
                channel_type=ch.channel_type,
                identifier=ch.identifier,
                phone_number=ch.phone_number,
            )
            for ch in channels
        ]
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tenants/{tenant_id}/flows", response_model=list[FlowResponse])
def list_flows(
    tenant_id: UUID = Path(...), session: Session = Depends(get_db_session)
) -> list[FlowResponse]:
    """List all flows for a tenant."""
    service = TenantService(session)
    try:
        flows = service.get_flows(tenant_id)
        return [
            FlowResponse(
                id=f.id,
                name=f.name,
                flow_id=f.flow_id,
                channel_instance_id=f.channel_instance_id,
            )
            for f in flows
        ]
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
