from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import String, TypeDecorator

if TYPE_CHECKING:
    from app.db.models import MessageDirection, MessageStatus


class EncryptedString(TypeDecorator):
    """SQLAlchemy type for encrypted string fields (GDPR/LGPD compliance)."""
    
    impl = String
    cache_ok = True
    _fernet_cache: Fernet | None = None
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
    
    @property
    def fernet(self) -> Fernet:
        """Lazy-load Fernet cipher to allow env vars to be loaded first."""
        if EncryptedString._fernet_cache is None:
            encryption_key = os.getenv("PII_ENCRYPTION_KEY")
            if not encryption_key:
                raise RuntimeError(
                    "PII_ENCRYPTION_KEY environment variable is required for encrypted fields. "
                    'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
                )
            EncryptedString._fernet_cache = Fernet(encryption_key.encode())
        return EncryptedString._fernet_cache
    
    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        """Encrypt value before storing in database."""
        if value is None:
            return None
        if isinstance(value, str):
            return self.fernet.encrypt(value.encode()).decode()
        return value
    
    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """Decrypt value when reading from database."""
        if value is None:
            return None
        if isinstance(value, memoryview):
            value = bytes(value).decode()
        elif isinstance(value, bytes):
            value = value.decode()
        if isinstance(value, str):
            return self.fernet.decrypt(value.encode()).decode()
        return value


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
