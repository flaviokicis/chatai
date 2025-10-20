from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.db.models import MessageDirection, MessageStatus


@dataclass(frozen=True, slots=True)
class MessageToSave:
    tenant_id: UUID
    channel_instance_id: UUID
    thread_id: UUID
    contact_id: UUID
    text: str
    direction: MessageDirection
    status: MessageStatus
    provider_message_id: str | None = None
    payload: dict[str, object] | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
