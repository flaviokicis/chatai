"""
API endpoints for managing human handoff requests.

Provides endpoints for:
- Fetching handoff requests by tenant
- Acknowledging handoff requests
- Filtering by acknowledgment status
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import HandoffRequest, Tenant
from app.db.session import get_db_session
from app.services.handoff_service import HandoffService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/handoffs", tags=["handoffs"])


class HandoffRequestResponse(BaseModel):
    """Response model for handoff requests."""
    
    id: UUID
    tenant_id: UUID
    flow_id: UUID | None
    thread_id: UUID | None
    contact_id: UUID | None
    channel_instance_id: UUID | None
    
    # Request details
    reason: str | None
    current_node_id: str | None
    user_message: str | None
    collected_answers: dict[str, Any] | None
    
    # Status tracking
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    
    # Context
    session_id: str | None
    conversation_context: dict[str, Any] | None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AcknowledgeHandoffRequest(BaseModel):
    """Request model for acknowledging a handoff."""
    
    handoff_id: UUID = Field(..., description="ID of the handoff request to acknowledge")


class HandoffListResponse(BaseModel):
    """Response model for handoff list with pagination."""
    
    handoffs: list[HandoffRequestResponse]
    total: int
    offset: int
    limit: int
    has_more: bool


@router.get("/tenants/{tenant_id}", response_model=HandoffListResponse)
async def get_handoff_requests(
    tenant_id: UUID = Path(..., description="Tenant ID"),
    acknowledged: bool | None = Query(
        None, 
        description="Filter by acknowledgment status. None=all, True=acknowledged, False=pending"
    ),
    limit: int = Query(50, ge=1, le=200, description="Number of handoffs to return"),
    offset: int = Query(0, ge=0, description="Number of handoffs to skip"),
    session: Session = Depends(get_db_session),
) -> HandoffListResponse:
    """
    Get handoff requests for the current tenant.
    
    Supports filtering by acknowledgment status and pagination.
    """
    try:
        handoff_service = HandoffService()
        
        # Get handoffs with filters
        handoffs = handoff_service.get_handoff_requests(
            tenant_id=tenant_id,
            acknowledged=acknowledged,
            limit=limit + 1,  # Get one extra to check if there are more
            offset=offset,
        )
        
        # Check if there are more results
        has_more = len(handoffs) > limit
        if has_more:
            handoffs = handoffs[:-1]  # Remove the extra item
        
        # Convert to response models
        handoff_responses = [
            HandoffRequestResponse.from_orm(handoff) 
            for handoff in handoffs
        ]
        
        # For total count, we'd need a separate query, but for now estimate
        total = offset + len(handoff_responses) + (1 if has_more else 0)
        
        return HandoffListResponse(
            handoffs=handoff_responses,
            total=total,
            offset=offset,
            limit=limit,
            has_more=has_more,
        )
        
    except Exception as e:
        logger.error(f"Failed to fetch handoff requests for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch handoff requests"
        )


@router.post("/tenants/{tenant_id}/acknowledge")
async def acknowledge_handoff(
    request: AcknowledgeHandoffRequest,
    tenant_id: UUID = Path(..., description="Tenant ID"),
) -> dict[str, Any]:
    """
    Acknowledge a handoff request.
    
    This marks the handoff as seen/acknowledged by the tenant.
    """
    try:
        handoff_service = HandoffService()
        
        # Verify the handoff belongs to this tenant
        with next(get_db_session()) as session:
            handoff = session.query(HandoffRequest).filter(
                HandoffRequest.id == request.handoff_id,
                HandoffRequest.tenant_id == tenant_id,
            ).first()
            
            if not handoff:
                raise HTTPException(
                    status_code=404,
                    detail="Handoff request not found"
                )
            
            if handoff.acknowledged_at is not None:
                return {
                    "success": True,
                    "message": "Handoff was already acknowledged",
                    "acknowledged_at": handoff.acknowledged_at.isoformat(),
                }
        
        # Acknowledge the handoff
        success = handoff_service.acknowledge_handoff(request.handoff_id)
        
        if success:
            return {
                "success": True,
                "message": "Handoff acknowledged successfully",
                "acknowledged_at": datetime.utcnow().isoformat(),
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to acknowledge handoff"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge handoff {request.handoff_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to acknowledge handoff"
        )


@router.get("/tenants/{tenant_id}/stats")
async def get_handoff_stats(
    tenant_id: UUID = Path(..., description="Tenant ID"),
) -> dict[str, Any]:
    """
    Get handoff statistics for the current tenant.
    """
    try:
        handoff_service = HandoffService()
        
        # Get counts for different statuses
        total_handoffs = handoff_service.get_handoff_requests(
            tenant_id=tenant_id,
            acknowledged=None,
            limit=1000,  # Large number to get rough count
            offset=0,
        )
        
        pending_handoffs = handoff_service.get_handoff_requests(
            tenant_id=tenant_id,
            acknowledged=False,
            limit=1000,
            offset=0,
        )
        
        acknowledged_handoffs = handoff_service.get_handoff_requests(
            tenant_id=tenant_id,
            acknowledged=True,
            limit=1000,
            offset=0,
        )
        
        return {
            "total": len(total_handoffs),
            "pending": len(pending_handoffs),
            "acknowledged": len(acknowledged_handoffs),
            "acknowledgment_rate": (
                len(acknowledged_handoffs) / len(total_handoffs)
                if total_handoffs else 0
            ),
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch handoff stats for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch handoff statistics"
        )
