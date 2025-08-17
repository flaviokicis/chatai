from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import repository
from app.db.models import ChatThread, Contact, ThreadStatus

logger = logging.getLogger(__name__)


class ChatServiceError(Exception):
    """Base exception for chat service errors."""


class ThreadNotFoundError(ChatServiceError):
    """Raised when a thread is not found."""


class ContactNotFoundError(ChatServiceError):
    """Raised when a contact is not found."""


class ChatService:
    """Service layer for chat management operations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_threads(
        self,
        tenant_id: UUID,
        *,
        channel_instance_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ChatThread]:
        """Get chat threads for a tenant with optional filtering."""
        return repository.get_threads_by_tenant(
            self.session,
            tenant_id,
            channel_instance_id=channel_instance_id,
            limit=limit,
            offset=offset,
        )

    def get_thread_detail(self, tenant_id: UUID, thread_id: UUID) -> ChatThread:
        """Get thread with messages, raising error if not found."""
        thread = repository.get_thread_with_messages(self.session, tenant_id, thread_id)
        if not thread:
            raise ThreadNotFoundError(f"Thread {thread_id} not found")
        return thread

    def get_contacts(
        self,
        tenant_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Contact]:
        """Get contacts for a tenant."""
        return repository.get_contacts_by_tenant(
            self.session, tenant_id, limit=limit, offset=offset
        )

    def update_thread_status(
        self, tenant_id: UUID, thread_id: UUID, status: ThreadStatus
    ) -> ChatThread:
        """Update thread status, raising error if not found."""
        thread = repository.update_thread_status(self.session, tenant_id, thread_id, status)
        if not thread:
            raise ThreadNotFoundError(f"Thread {thread_id} not found")

        try:
            self.session.commit()
            logger.info("Updated thread %d status to %s", thread_id, status.value)
            return thread
        except Exception as exc:
            self.session.rollback()
            logger.error("Failed to update thread status: %s", exc)
            raise ChatServiceError("Failed to update thread status") from exc

    def update_contact_consent(self, tenant_id: UUID, contact_id: UUID, action: str) -> Contact:
        """Update contact consent status for GDPR/LGPD compliance."""
        if action not in {"opt_in", "revoke", "request_erasure"}:
            raise ChatServiceError(f"Invalid consent action: {action}")

        contact = repository.update_contact_consent(self.session, tenant_id, contact_id, action)
        if not contact:
            raise ContactNotFoundError(f"Contact {contact_id} not found")

        try:
            self.session.commit()
            logger.info("Updated contact %d consent: %s", contact_id, action)
            return contact
        except Exception as exc:
            self.session.rollback()
            logger.error("Failed to update contact consent: %s", exc)
            raise ChatServiceError("Failed to update contact consent") from exc
