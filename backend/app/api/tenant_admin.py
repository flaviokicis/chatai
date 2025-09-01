"""API endpoints for tenant admin phone management."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.services.admin_phone_service import AdminPhoneService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenant_admin"])


class UpdateAdminPhonesRequest(BaseModel):
    admin_phone_numbers: list[str]


class AdminPhonesResponse(BaseModel):
    admin_phone_numbers: list[str]


@router.get("/{tenant_id}/admin-phones", response_model=AdminPhonesResponse)
def get_admin_phones(
    tenant_id: UUID,
    session: Session = Depends(get_db_session),
) -> AdminPhonesResponse:
    """Get admin phone numbers for a tenant."""
    try:
        admin_service = AdminPhoneService(session)
        admin_phones = admin_service.list_admin_phones(tenant_id)
        return AdminPhonesResponse(admin_phone_numbers=admin_phones)
    except Exception as e:
        logger.error(f"Error getting admin phones for tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get admin phones")


@router.put("/{tenant_id}/admin-phones", response_model=AdminPhonesResponse)
def update_admin_phones(
    tenant_id: UUID,
    request: UpdateAdminPhonesRequest,
    session: Session = Depends(get_db_session),
) -> AdminPhonesResponse:
    """Update admin phone numbers for a tenant."""
    try:
        from app.db.models import Tenant
        from sqlalchemy.orm.attributes import flag_modified
        
        # Get tenant
        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Update admin phone numbers
        tenant.admin_phone_numbers = request.admin_phone_numbers
        flag_modified(tenant, 'admin_phone_numbers')
        session.commit()
        
        logger.info(f"Updated admin phones for tenant {tenant_id}: {request.admin_phone_numbers}")
        
        return AdminPhonesResponse(admin_phone_numbers=request.admin_phone_numbers)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating admin phones for tenant {tenant_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Failed to update admin phones")
