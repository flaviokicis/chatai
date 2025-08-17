from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    ChatThread,
    Contact,
    Message,
    MessageDirection,
    MessageStatus,
    ThreadStatus,
)
from app.db.session import get_db_session
from app.services.chat_service import (
    ChatService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["chats"])


class ContactResponse(BaseModel):
    id: UUID
    external_id: str
    display_name: str | None
    phone_number: str | None
    created_at: datetime
    consent_opt_in_at: datetime | None
    consent_revoked_at: datetime | None


class ThreadResponse(BaseModel):
    id: UUID
    status: ThreadStatus
    subject: str | None
    last_message_at: datetime | None
    created_at: datetime
    contact: ContactResponse


class MessageResponse(BaseModel):
    id: UUID
    direction: MessageDirection
    status: MessageStatus
    text: str | None
    created_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None
    provider_message_id: str | None


class ThreadDetailResponse(ThreadResponse):
    messages: list[MessageResponse]


@router.get("/tenants/{tenant_id}/threads", response_model=list[ThreadResponse])
def list_threads(
    tenant_id: UUID = Path(...),
    channel_instance_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db_session),
) -> list[ThreadResponse]:
    """List chat threads for a tenant, optionally filtered by channel instance."""
    service = ChatService(session)
    threads = service.get_threads(
        tenant_id, channel_instance_id=channel_instance_id, limit=limit, offset=offset
    )
    return [
        ThreadResponse(
            id=t.id,
            status=t.status,
            subject=t.subject,
            last_message_at=t.last_message_at,
            created_at=t.created_at,
            contact=ContactResponse(
                id=t.contact.id,
                external_id=t.contact.external_id,
                display_name=t.contact.display_name,
                phone_number=t.contact.phone_number,
                created_at=t.contact.created_at,
                consent_opt_in_at=t.contact.consent_opt_in_at,
                consent_revoked_at=t.contact.consent_revoked_at,
            ),
        )
        for t in threads
    ]


@router.get("/tenants/{tenant_id}/threads/{thread_id}", response_model=ThreadDetailResponse)
def get_thread_detail(
    tenant_id: UUID = Path(...),
    thread_id: UUID = Path(...),
    session=Depends(get_db_session),
) -> Any:
    """Get detailed thread information including all messages."""
    try:
        Base.metadata.create_all(bind=session.get_bind())

        thread = (
            session.query(ChatThread)
            .join(Contact)
            .filter(
                ChatThread.id == thread_id,
                ChatThread.tenant_id == tenant_id,
                ChatThread.deleted_at.is_(None),
                Contact.deleted_at.is_(None),
            )
            .first()
        )

        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        messages = (
            session.query(Message)
            .filter(
                Message.thread_id == thread_id,
                Message.deleted_at.is_(None),
            )
            .order_by(Message.id)
            .all()
        )

        return ThreadDetailResponse(
            id=thread.id,
            status=thread.status,
            subject=thread.subject,
            last_message_at=thread.last_message_at,
            created_at=thread.created_at,
            contact=ContactResponse(
                id=thread.contact.id,
                external_id=thread.contact.external_id,
                display_name=thread.contact.display_name,
                phone_number=thread.contact.phone_number,
                created_at=thread.contact.created_at,
                consent_opt_in_at=thread.contact.consent_opt_in_at,
                consent_revoked_at=thread.contact.consent_revoked_at,
            ),
            messages=[
                MessageResponse(
                    id=m.id,
                    direction=m.direction,
                    status=m.status,
                    text=m.text,
                    created_at=m.created_at,
                    sent_at=m.sent_at,
                    delivered_at=m.delivered_at,
                    read_at=m.read_at,
                    provider_message_id=m.provider_message_id,
                )
                for m in messages
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Failed to get thread detail: {exc}")


@router.get("/tenants/{tenant_id}/contacts", response_model=list[ContactResponse])
def list_contacts(
    tenant_id: UUID = Path(...),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session=Depends(get_db_session),
) -> Any:
    """List contacts for a tenant."""
    try:
        Base.metadata.create_all(bind=session.get_bind())

        contacts = (
            session.query(Contact)
            .filter(
                Contact.tenant_id == tenant_id,
                Contact.deleted_at.is_(None),
            )
            .order_by(desc(Contact.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [
            ContactResponse(
                id=c.id,
                external_id=c.external_id,
                display_name=c.display_name,
                phone_number=c.phone_number,
                created_at=c.created_at,
                consent_opt_in_at=c.consent_opt_in_at,
                consent_revoked_at=c.consent_revoked_at,
            )
            for c in contacts
        ]
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Failed to list contacts: {exc}")


class UpdateThreadStatusRequest(BaseModel):
    status: ThreadStatus


@router.patch("/tenants/{tenant_id}/threads/{thread_id}/status")
def update_thread_status(
    payload: UpdateThreadStatusRequest,
    tenant_id: UUID = Path(...),
    thread_id: UUID = Path(...),
    session=Depends(get_db_session),
) -> dict[str, str]:
    """Update thread status (open/closed/archived)."""
    try:
        Base.metadata.create_all(bind=session.get_bind())

        thread = (
            session.query(ChatThread)
            .filter(
                ChatThread.id == thread_id,
                ChatThread.tenant_id == tenant_id,
                ChatThread.deleted_at.is_(None),
            )
            .first()
        )

        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        thread.status = payload.status
        session.commit()

        return {"status": "updated"}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update thread status: {exc}")


class ContactConsentRequest(BaseModel):
    action: str  # "opt_in", "revoke", "request_erasure"


@router.post("/tenants/{tenant_id}/contacts/{contact_id}/consent")
def update_contact_consent(
    payload: ContactConsentRequest,
    tenant_id: UUID = Path(...),
    contact_id: UUID = Path(...),
    session=Depends(get_db_session),
) -> dict[str, str]:
    """Update contact consent status for GDPR/LGPD compliance."""
    try:
        Base.metadata.create_all(bind=session.get_bind())

        contact = (
            session.query(Contact)
            .filter(
                Contact.id == contact_id,
                Contact.tenant_id == tenant_id,
                Contact.deleted_at.is_(None),
            )
            .first()
        )

        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        now = datetime.utcnow()

        if payload.action == "opt_in":
            contact.consent_opt_in_at = now
            contact.consent_revoked_at = None
        elif payload.action == "revoke":
            contact.consent_revoked_at = now
        elif payload.action == "request_erasure":
            contact.erasure_requested_at = now
        else:
            raise HTTPException(status_code=400, detail="Invalid action")

        session.commit()

        return {"status": "updated", "action": payload.action}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update consent: {exc}")
