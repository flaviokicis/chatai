"""
DATABASE MODELS - GDPR/LGPD ENCRYPTION GUIDELINES
================================================

⚠️  CRITICAL: This file contains sensitive personal data that MUST be encrypted for GDPR/LGPD compliance.

ENCRYPTION RULES FOR PERSONAL DATA:
==================================

🔐 MUST BE ENCRYPTED (use EncryptedString):
-------------------------------------------
✅ Names: first_name, last_name, display_name, full_name
✅ Contact Info: email, phone_number, address, postal_code
✅ Identifiers: external_id (if contains PII), user_id (if contains PII)
✅ Communication: message text, chat content, conversation data
✅ Profile Data: bio, description, profile_info, preferences
✅ Location: specific addresses, GPS coordinates
✅ Financial: account numbers, payment info, billing details
✅ Health: medical info, health status, treatment details
✅ Biometric: photos, fingerprints, voice data
✅ Behavioral: tracking data, usage patterns, preferences

📝 EXAMPLES OF ENCRYPTED FIELDS:
- owner_first_name, owner_last_name (tenant owner names)
- phone_number (contact phone numbers)
- display_name (user display names)
- message.text (conversation content)
- external_id (if format like "whatsapp:+5511999999999")

🔓 CAN REMAIN UNENCRYPTED:
--------------------------
✅ System Metadata: created_at, updated_at, id, tenant_id
✅ Non-PII Enums: status, type, category (if not revealing personal info)
✅ Technical Data: API keys (if not linked to individuals), configuration
✅ Aggregated Data: counts, statistics (if anonymized)
✅ Public Data: company names, public URLs, published content
✅ System State: flow_state, processing_status, system_flags

📝 EXAMPLES OF UNENCRYPTED FIELDS:
- id, tenant_id, created_at, updated_at
- channel_type (enum: whatsapp, sms, etc.)
- message_status (enum: sent, delivered, read)
- flow_id, node_id (system identifiers)

⚠️  WHEN IN DOUBT: ENCRYPT IT!
==============================
If a field might contain personal information or could be used to identify
an individual, encrypt it. It's better to over-encrypt than risk GDPR/LGPD violations.

IMPLEMENTATION:
===============
- Use: mapped_column(EncryptedString, nullable=False)
- Not: mapped_column(String(255), nullable=False)
- Requires: PII_ENCRYPTION_KEY environment variable
- Migration: Required when changing String -> EncryptedString

CURRENT ENCRYPTION STATUS:
=========================
✅ Tenant.owner_email - ENCRYPTED
✅ Tenant.owner_first_name - ENCRYPTED (FIXED)
✅ Tenant.owner_last_name - ENCRYPTED (FIXED)
✅ ChannelInstance.phone_number - ENCRYPTED
✅ Contact.phone_number - ENCRYPTED (FIXED)
✅ Contact.display_name - ENCRYPTED (FIXED)
✅ Contact.external_id - ENCRYPTED (FIXED)
✅ Message.text - ENCRYPTED

🎉 ALL PERSONAL DATA IS NOW GDPR/LGPD COMPLIANT! 🎉
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean,
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
    # Owner/admin contact for the tenant (GDPR/LGPD: Names are PII and must be encrypted)
    owner_first_name: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    owner_last_name: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    owner_email: Mapped[str] = mapped_column(EncryptedString, nullable=False)

    # Admin phone numbers that can modify flows during conversations (GDPR/LGPD: Phone numbers are PII)
    # Stored as list of encrypted phone numbers, e.g., ["+5511999999999", "+5511888888888"]
    admin_phone_numbers: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

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

    wait_time_before_replying_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    typing_indicator_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_typing_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    max_typing_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    message_reset_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    natural_delays_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    delay_variance_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=20)

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
    # Optimistic locking version
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    channel_instance: Mapped[ChannelInstance] = relationship(back_populates="flows")
    versions: Mapped[list[FlowVersion]] = relationship(
        back_populates="flow",
        cascade="all, delete-orphan",
        order_by="FlowVersion.version_number.desc()",
    )


class FlowVersion(Base, TimestampMixin):
    """Stores historical versions of flow definitions for change tracking and undo."""

    __tablename__ = "flow_versions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    flow_id: Mapped[UUID] = mapped_column(ForeignKey("flows.id", ondelete="CASCADE"))

    # Version tracking
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # User tracking (optional, could be expanded later)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    flow: Mapped[Flow] = relationship(back_populates="versions")


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id", name="uq_contact_external"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))

    # Cross-channel identifier, e.g., "whatsapp:+5511999999999"; immutable key (GDPR/LGPD: Contains PII)
    external_id: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    # Optional display name from the provider profile (GDPR/LGPD: Names are PII)
    display_name: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    # Raw number if available; stored for convenience/minimization (GDPR/LGPD: Phone numbers are PII)
    phone_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)

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

    # Flow completion and human handoff tracking
    flow_completion_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    human_handoff_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    human_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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


class FlowChatSession(Base, TimestampMixin):
    """Tracks chat session metadata per flow, including clear history."""

    __tablename__ = "flow_chat_sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    flow_id: Mapped[UUID] = mapped_column(ForeignKey("flows.id", ondelete="CASCADE"), unique=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HandoffRequest(Base, TimestampMixin):
    """Tracks human handoff requests for reliable processing and acknowledgment."""

    __tablename__ = "handoff_requests"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    flow_id: Mapped[UUID | None] = mapped_column(ForeignKey("flows.id", ondelete="SET NULL"))
    thread_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="SET NULL")
    )
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    channel_instance_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("channel_instances.id", ondelete="SET NULL")
    )

    # Request details
    reason: Mapped[dict | None] = mapped_column(JSONB)  # Why handoff was requested
    current_node_id: Mapped[str | None] = mapped_column(String(255))  # Where in flow
    user_message: Mapped[str | None] = mapped_column(EncryptedString)  # Last user message
    collected_answers: Mapped[dict | None] = mapped_column(JSONB)  # Flow progress so far

    # Status tracking
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Context preservation
    session_id: Mapped[str | None] = mapped_column(String(255))  # Flow session
    conversation_context: Mapped[dict | None] = mapped_column(JSONB)  # Additional context

    # Relationships
    tenant: Mapped[Tenant] = relationship()
    flow: Mapped[Flow | None] = relationship()
    thread: Mapped[ChatThread | None] = relationship()
    contact: Mapped[Contact | None] = relationship()
    channel_instance: Mapped[ChannelInstance | None] = relationship()


# --- Agent Thought Tracing Models ---


# Thought tracing models removed - using Langfuse for observability instead
