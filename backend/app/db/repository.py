from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    ChannelInstance,
    ChatThread,
    Contact,
    Flow,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantProjectConfig,
    ThreadStatus,
)


def find_channel_instance_by_identifier(
    session: Session, identifier: str
) -> ChannelInstance | None:
    return session.execute(
        select(ChannelInstance).where(ChannelInstance.identifier == identifier)
    ).scalar_one_or_none()


def get_or_create_contact(
    session: Session,
    tenant_id: UUID,
    external_id: str,
    *,
    phone_number: str | None,
    display_name: str | None,
) -> Contact:
    contact = session.execute(
        select(Contact).where(Contact.tenant_id == tenant_id, Contact.external_id == external_id)
    ).scalar_one_or_none()
    if contact is None:
        contact = Contact(
            tenant_id=tenant_id,
            external_id=external_id,
            phone_number=phone_number,
            display_name=display_name,
        )
        session.add(contact)
        session.flush()
    else:
        # Update minimally useful info if missing
        if not contact.phone_number and phone_number:
            contact.phone_number = phone_number
        if not contact.display_name and display_name:
            contact.display_name = display_name
    return contact


def get_or_create_thread(
    session: Session,
    *,
    tenant_id: UUID,
    channel_instance_id: UUID,
    contact_id: UUID,
    flow_id: UUID | None,
) -> ChatThread:
    thread = session.execute(
        select(ChatThread).where(
            ChatThread.tenant_id == tenant_id,
            ChatThread.channel_instance_id == channel_instance_id,
            ChatThread.contact_id == contact_id,
        )
    ).scalar_one_or_none()
    if thread is None:
        thread = ChatThread(
            tenant_id=tenant_id,
            channel_instance_id=channel_instance_id,
            contact_id=contact_id,
            flow_id=flow_id,
            status=ThreadStatus.open,
            last_message_at=datetime.now(UTC),
        )
        session.add(thread)
        session.flush()
    else:
        thread.last_message_at = datetime.now(UTC)
        if flow_id and not thread.flow_id:
            thread.flow_id = flow_id
    return thread


def create_message(
    session: Session,
    *,
    tenant_id: UUID,
    channel_instance_id: UUID,
    thread_id: UUID,
    contact_id: UUID | None,
    text: str | None,
    direction: MessageDirection,
    provider_message_id: str | None = None,
    payload: dict | None = None,
    status: MessageStatus = MessageStatus.sent,
    sent_at: datetime | None = None,
    delivered_at: datetime | None = None,
    read_at: datetime | None = None,
) -> Message:
    message = Message(
        tenant_id=tenant_id,
        channel_instance_id=channel_instance_id,
        thread_id=thread_id,
        contact_id=contact_id,
        text=text,
        direction=direction,
        provider_message_id=provider_message_id,
        payload=payload,
        status=status,
        sent_at=sent_at,
        delivered_at=delivered_at,
        read_at=read_at,
    )
    session.add(message)
    session.flush()
    return message


# --- Tenant Repository Functions ---


def create_tenant_with_config(
    session: Session,
    *,
    first_name: str,
    last_name: str,
    email: str,
    project_description: str | None = None,
    target_audience: str | None = None,
    communication_style: str | None = None,
) -> Tenant:
    """Create a tenant with associated project configuration."""
    tenant = Tenant(
        owner_first_name=first_name,
        owner_last_name=last_name,
        owner_email=email,
    )
    session.add(tenant)
    session.flush()

    config = TenantProjectConfig(
        tenant_id=tenant.id,
        project_description=project_description,
        target_audience=target_audience,
        communication_style=communication_style,
    )
    session.add(config)
    session.flush()
    return tenant


def get_active_tenants(session: Session) -> Sequence[Tenant]:
    """Get all active tenants."""
    return (
        session.execute(select(Tenant).where(Tenant.deleted_at.is_(None)).order_by(Tenant.id))
        .scalars()
        .all()
    )


def get_tenant_by_id(session: Session, tenant_id: UUID) -> Tenant | None:
    """Get tenant by ID with project config loaded."""
    return session.execute(
        select(Tenant)
        .options(selectinload(Tenant.project_config))
        .where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    ).scalar_one_or_none()


def update_tenant_project_config(
    session: Session,
    *,
    tenant_id: UUID,
    project_description: str | None = None,
    target_audience: str | None = None,
    communication_style: str | None = None,
) -> Tenant | None:
    """Update tenant project configuration."""
    from app.db.models import TenantProjectConfig

    tenant = session.execute(
        select(Tenant)
        .options(selectinload(Tenant.project_config))
        .where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    ).scalar_one_or_none()

    if not tenant:
        return None

    if tenant.project_config:
        # Update existing config
        tenant.project_config.project_description = project_description
        tenant.project_config.target_audience = target_audience
        tenant.project_config.communication_style = communication_style
    else:
        # Create new config if it doesn't exist
        config = TenantProjectConfig(
            tenant_id=tenant_id,
            project_description=project_description,
            target_audience=target_audience,
            communication_style=communication_style,
        )
        session.add(config)

    session.flush()
    return tenant


# --- Channel Instance Repository Functions ---


def create_channel_instance(
    session: Session,
    *,
    tenant_id: UUID,
    channel_type: str,
    identifier: str,
    phone_number: str | None = None,
    extra: dict | None = None,
) -> ChannelInstance:
    """Create a new channel instance."""
    channel = ChannelInstance(
        tenant_id=tenant_id,
        channel_type=channel_type,  # type: ignore[arg-type]
        identifier=identifier,
        phone_number=phone_number,
        extra=extra,
    )
    session.add(channel)
    session.flush()
    return channel


def get_channel_instances_by_tenant(session: Session, tenant_id: UUID) -> Sequence[ChannelInstance]:
    """Get all active channel instances for a tenant."""
    return (
        session.execute(
            select(ChannelInstance)
            .where(
                ChannelInstance.tenant_id == tenant_id,
                ChannelInstance.deleted_at.is_(None),
            )
            .order_by(ChannelInstance.id)
        )
        .scalars()
        .all()
    )


def update_channel_instance_phone_number(
    session: Session,
    channel_id: UUID,
    new_phone_number: str,
    new_identifier: str | None = None,
) -> ChannelInstance | None:
    """Update the phone number and optionally identifier of a channel instance."""
    channel = session.execute(
        select(ChannelInstance).where(
            ChannelInstance.id == channel_id,
            ChannelInstance.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if channel:
        channel.phone_number = new_phone_number
        if new_identifier:
            channel.identifier = new_identifier
        session.flush()

    return channel


# --- Flow Repository Functions ---


def create_flow(
    session: Session,
    *,
    tenant_id: UUID,
    channel_instance_id: UUID,
    name: str,
    flow_id: str,
    definition: dict,
) -> Flow:
    """Create a new flow."""
    flow = Flow(
        tenant_id=tenant_id,
        channel_instance_id=channel_instance_id,
        name=name,
        flow_id=flow_id,
        definition=definition,
        is_active=True,
    )
    session.add(flow)
    session.flush()
    return flow


def get_flows_by_tenant(session: Session, tenant_id: UUID) -> Sequence[Flow]:
    """Get all active flows for a tenant."""
    return (
        session.execute(
            select(Flow)
            .where(Flow.tenant_id == tenant_id, Flow.deleted_at.is_(None))
            .order_by(Flow.id)
        )
        .scalars()
        .all()
    )


# --- Chat Repository Functions ---


def get_threads_by_tenant(
    session: Session,
    tenant_id: UUID,
    *,
    channel_instance_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[ChatThread]:
    """Get chat threads for a tenant with optional filtering."""
    query = (
        select(ChatThread)
        .options(selectinload(ChatThread.contact))
        .where(
            ChatThread.tenant_id == tenant_id,
            ChatThread.deleted_at.is_(None),
        )
    )

    if channel_instance_id:
        query = query.where(ChatThread.channel_instance_id == channel_instance_id)

    return (
        session.execute(
            query.order_by(desc(ChatThread.last_message_at)).offset(offset).limit(limit)
        )
        .scalars()
        .all()
    )


def get_thread_with_messages(
    session: Session, tenant_id: UUID, thread_id: UUID
) -> ChatThread | None:
    """Get a thread with all messages and contact info."""
    return session.execute(
        select(ChatThread)
        .options(
            selectinload(ChatThread.contact),
            selectinload(ChatThread.messages),
        )
        .where(
            ChatThread.id == thread_id,
            ChatThread.tenant_id == tenant_id,
            ChatThread.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def get_contacts_by_tenant(
    session: Session,
    tenant_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[Contact]:
    """Get contacts for a tenant."""
    return (
        session.execute(
            select(Contact)
            .where(
                Contact.tenant_id == tenant_id,
                Contact.deleted_at.is_(None),
            )
            .order_by(desc(Contact.created_at))
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )


def update_thread_status(
    session: Session, tenant_id: UUID, thread_id: UUID, status: ThreadStatus
) -> ChatThread | None:
    """Update thread status."""
    thread = session.execute(
        select(ChatThread).where(
            ChatThread.id == thread_id,
            ChatThread.tenant_id == tenant_id,
            ChatThread.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if thread:
        thread.status = status
        session.flush()

    return thread


def update_contact_consent(
    session: Session,
    tenant_id: UUID,
    contact_id: UUID,
    action: str,
) -> Contact | None:
    """Update contact consent for GDPR/LGPD compliance."""
    contact = session.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id,
            Contact.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if not contact:
        return None

    now = datetime.now(UTC)

    if action == "opt_in":
        contact.consent_opt_in_at = now
        contact.consent_revoked_at = None
    elif action == "revoke":
        contact.consent_revoked_at = now
    elif action == "request_erasure":
        contact.erasure_requested_at = now

    session.flush()
    return contact
