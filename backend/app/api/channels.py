"""User-accessible channel endpoints (no admin auth required)."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.repository import get_channel_instances_by_tenant, get_flows_by_channel_instance
from app.db.session import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channels", tags=["channels"])


class FlowData(BaseModel):
    id: str
    name: str
    flow_id: str
    channel_instance_id: str
    is_active: bool


class ChannelResponse(BaseModel):
    id: str  # Convert UUID to string for frontend
    channel_type: str
    identifier: str
    phone_number: str | None
    flows: list[FlowData] = []


@router.get("/tenant/{tenant_id}", response_model=list[ChannelResponse])
async def list_tenant_channels(
    tenant_id: UUID,
    session: Session = Depends(get_db_session),
) -> list[ChannelResponse]:
    """List channels for a tenant (user-accessible, no admin auth required)."""
    try:
        channels = get_channel_instances_by_tenant(session, tenant_id)

        result = []
        for channel in channels:
            # Get flows for this channel
            flows = get_flows_by_channel_instance(session, channel.id)
            flows_data = [
                FlowData(
                    id=str(flow.id),
                    name=flow.name,
                    flow_id=flow.flow_id,
                    channel_instance_id=str(flow.channel_instance_id),
                    is_active=flow.is_active,
                )
                for flow in flows
            ]

            result.append(
                ChannelResponse(
                    id=str(channel.id),
                    channel_type=channel.channel_type.value,
                    identifier=channel.identifier,
                    phone_number=channel.phone_number,
                    flows=flows_data,
                )
            )

        return result

    except Exception as e:
        logger.error(f"Error listing channels for tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list channels")
