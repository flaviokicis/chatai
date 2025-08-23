from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as PgEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid_v7.base import uuid7

from app.db.base import Base
from app.db.types import EncryptedString

# --- Enumerations


class ChannelType(str, Enum):
    whatsapp = "whatsapp"
    instagram_dm = "instagram_dm"


class ThreadStatus(str, Enum):
    open = "open"
    closed = "closed"
    archived = "archived"


class MessageDirection(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class MessageStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class FlowChatRole(str, Enum):
    """Participant role in a flow editor chat."""

    user = "user"
    assistant = "assistant"
    system = "system"


# --- Base mixins


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Core entities


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    # Owner/admin contact for the tenant
    owner_first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_email: Mapped[str] = mapped_column(EncryptedString, nullable=False)

    # One-to-one project config
    project_config: Mapped[TenantProjectConfig] = relationship(
        back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )
    # Channel instances (e.g., WhatsApp numbers)
    channel_instances: Mapped[list[ChannelInstance]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    # Contacts and threads/messages
    contacts: Mapped[list[Contact]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class TenantProjectConfig(Base, TimestampMixin):
    __tablename__ = "tenant_project_configs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), unique=True
    )

    # Descriptions provided by the user (free text)
    project_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    communication_style: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="project_config")


class ChannelInstance(Base, TimestampMixin):
    __tablename__ = "channel_instances"
    __table_args__ = (
        UniqueConstraint("tenant_id", "identifier", name="uq_channel_instance_identifier"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))

    channel_type: Mapped[ChannelType] = mapped_column(PgEnum(ChannelType, name="channel_type"))
    # Example: "whatsapp:+14155238886"
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    # Convenience copy (e.g., "+14155238886"); may be null for channels without numbers
    phone_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    # Provider/config metadata (Twilio SID, webhook secrets, etc.)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="channel_instances")
    flows: Mapped[list[Flow]] = relationship(
        back_populates="channel_instance", cascade="all, delete-orphan"
    )
    threads: Mapped[list[ChatThread]] = relationship(
        back_populates="channel_instance", cascade="all, delete-orphan"
    )


class Flow(Base, TimestampMixin):
    __tablename__ = "flows"
    __table_args__ = (UniqueConstraint("tenant_id", "flow_id", name="uq_flow_tenant_flow_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    channel_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("channel_instances.id", ondelete="CASCADE")
    )

    # Human and programmatic identifiers
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    flow_id: Mapped[str] = mapped_column(String(200), nullable=False)
    # The full flow definition (see backend/playground/flow_example.json)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    channel_instance: Mapped[ChannelInstance] = relationship(back_populates="flows")


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id", name="uq_contact_external"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))

    # Cross-channel identifier, e.g., "whatsapp:+5511999999999"; immutable key
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Optional display name from the provider profile
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Raw number if available; stored for convenience/minimization
    phone_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # GDPR/consent tracking
    consent_opt_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erasure_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant: Mapped[Tenant] = relationship(back_populates="contacts")
    threads: Mapped[list[ChatThread]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )


class ChatThread(Base, TimestampMixin):
    __tablename__ = "chat_threads"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "channel_instance_id",
            "contact_id",
            name="uq_thread_unique_per_contact_channel",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    channel_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("channel_instances.id", ondelete="CASCADE")
    )
    contact_id: Mapped[UUID] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    flow_id: Mapped[UUID | None] = mapped_column(ForeignKey("flows.id", ondelete="SET NULL"))

    status: Mapped[ThreadStatus] = mapped_column(PgEnum(ThreadStatus, name="thread_status"))
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    channel_instance: Mapped[ChannelInstance] = relationship(back_populates="threads")
    contact: Mapped[Contact] = relationship(back_populates="threads")
    messages: Mapped[list[Message]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    channel_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("channel_instances.id", ondelete="CASCADE")
    )
    thread_id: Mapped[UUID] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"))
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))

    direction: Mapped[MessageDirection] = mapped_column(
        PgEnum(MessageDirection, name="message_direction"), nullable=False
    )
    status: Mapped[MessageStatus] = mapped_column(
        PgEnum(MessageStatus, name="message_status"), nullable=False, default=MessageStatus.sent
    )

    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str | None] = mapped_column(EncryptedString)
    # Delivery timestamps
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Optional quoted/replied message reference (provider id or local id)
    quoted_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))

    # Structured data for buttons/templates, etc.
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    thread: Mapped[ChatThread] = relationship(back_populates="messages", foreign_keys=[thread_id])
    attachments: Mapped[list[MessageAttachment]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class MessageAttachment(Base, TimestampMixin):
    __tablename__ = "message_attachments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    media_type: Mapped[str] = mapped_column(String(40), nullable=False)  # image, audio, video, doc
    content_type: Mapped[str | None] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column(Text)  # storage location or provider URL
    file_name: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    attachment_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    message: Mapped[Message] = relationship(back_populates="attachments")


class FlowChatMessage(Base, TimestampMixin):
    """Stores messages exchanged in the flow editor chat."""

    __tablename__ = "flow_chat_messages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    flow_id: Mapped[UUID] = mapped_column(ForeignKey("flows.id", ondelete="CASCADE"))
    role: Mapped[FlowChatRole] = mapped_column(PgEnum(FlowChatRole, name="flow_chat_role"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
