from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    ChannelInstance,
    ChannelType,
    ChatThread,
    Contact,
    Flow,
    FlowChatMessage,
    FlowChatRole,
    FlowChatSession,
    FlowVersion,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantProjectConfig,
    ThreadStatus,
)

logger = logging.getLogger(__name__)


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


def create_flow_chat_message(
    session: Session,
    *,
    flow_id: UUID,
    role: FlowChatRole,
    content: str,
) -> FlowChatMessage:
    """Persist a flow editor chat message."""

    message = FlowChatMessage(flow_id=flow_id, role=role, content=content)
    session.add(message)
    session.flush()
    return message


def list_flow_chat_messages(session: Session, flow_id: UUID) -> Sequence[FlowChatMessage]:
    """Return all chat messages for a flow ordered by creation time, excluding cleared messages."""
    
    # Get the latest cleared_at timestamp for this flow
    chat_session = session.execute(
        select(FlowChatSession).where(FlowChatSession.flow_id == flow_id)
    ).scalars().first()
    
    cleared_at = chat_session.cleared_at if chat_session else None
    
    query = select(FlowChatMessage).where(
        FlowChatMessage.flow_id == flow_id,
        FlowChatMessage.deleted_at.is_(None),
    )
    
    # Only show messages created after the last clear
    if cleared_at:
        query = query.where(FlowChatMessage.created_at > cleared_at)
    
    return (
        session.execute(query.order_by(FlowChatMessage.created_at))
        .scalars()
        .all()
    )


def get_latest_assistant_message(
    session: Session, flow_id: UUID
) -> FlowChatMessage | None:
    # Get the latest cleared_at timestamp for this flow
    chat_session = session.execute(
        select(FlowChatSession).where(FlowChatSession.flow_id == flow_id)
    ).scalars().first()
    
    cleared_at = chat_session.cleared_at if chat_session else None
    
    query = select(FlowChatMessage).where(
        FlowChatMessage.flow_id == flow_id,
        FlowChatMessage.role == FlowChatRole.assistant,
        FlowChatMessage.deleted_at.is_(None),
    )
    
    # Only show messages created after the last clear
    if cleared_at:
        query = query.where(FlowChatMessage.created_at > cleared_at)
    
    return (
        session.execute(query.order_by(desc(FlowChatMessage.created_at)))
        .scalars()
        .first()
    )


def clear_flow_chat_messages(session: Session, flow_id: UUID) -> None:
    """Mark the flow chat as cleared by setting cleared_at timestamp."""
    from datetime import datetime, timezone
    
    # Get or create the chat session record
    chat_session = session.execute(
        select(FlowChatSession).where(FlowChatSession.flow_id == flow_id)
    ).scalars().first()
    
    if not chat_session:
        chat_session = FlowChatSession(flow_id=flow_id)
        session.add(chat_session)
    
    # Set cleared_at to current timestamp
    chat_session.cleared_at = datetime.now(timezone.utc)
    session.flush()


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


def get_channel_instance_by_id(session: Session, channel_id: UUID) -> ChannelInstance | None:
    """Get a channel instance by its ID."""
    return session.execute(
        select(ChannelInstance)
        .where(ChannelInstance.id == channel_id, ChannelInstance.deleted_at.is_(None))
    ).scalar_one_or_none()


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
    # Check if this channel already has any flows
    existing_flows = get_flows_by_channel_instance(session, channel_instance_id)
    # Only make this flow active if it's the first one for this channel
    is_first_flow = len(existing_flows) == 0
    
    flow = Flow(
        tenant_id=tenant_id,
        channel_instance_id=channel_instance_id,
        name=name,
        flow_id=flow_id,
        definition=definition,
        is_active=is_first_flow,  # Only active if it's the first flow for this channel
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


def get_flows_by_channel_instance(session: Session, channel_instance_id: UUID) -> Sequence[Flow]:
    """Get all flows for a specific channel instance."""
    return (
        session.execute(
            select(Flow)
            .where(Flow.channel_instance_id == channel_instance_id, Flow.deleted_at.is_(None))
            .order_by(Flow.id)
        )
        .scalars()
        .all()
    )


def get_flow_by_id(session: Session, flow_id: UUID) -> Flow | None:
    """Get a specific flow by its ID."""
    return session.execute(
        select(Flow)
        .where(Flow.id == flow_id, Flow.deleted_at.is_(None))
    ).scalar_one_or_none()


def update_flow(
    session: Session,
    flow_id: UUID,
    *,
    name: str | None = None,
    definition: dict | None = None,
    is_active: bool | None = None,
) -> Flow | None:
    """Update an existing flow."""
    flow = session.execute(
        select(Flow).where(Flow.id == flow_id, Flow.deleted_at.is_(None))
    ).scalar_one_or_none()

    if not flow:
        return None

    # Update fields if provided
    if name is not None:
        flow.name = name
    if definition is not None:
        flow.definition = definition
    if is_active is not None:
        flow.is_active = is_active

    session.flush()
    return flow


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


def get_threads_needing_human_review(session: Session, tenant_id: UUID | None = None) -> list[ChatThread]:
    """Get threads that have requested human handoff but haven't been reviewed yet."""
    query = select(ChatThread).where(
        ChatThread.human_handoff_requested_at.is_not(None),
        ChatThread.human_reviewed_at.is_(None),
    )
    
    if tenant_id:
        query = query.where(ChatThread.tenant_id == tenant_id)
    
    return list(session.execute(query.order_by(ChatThread.human_handoff_requested_at.desc())).scalars())


def get_completed_threads(session: Session, tenant_id: UUID | None = None) -> list[ChatThread]:
    """Get threads that have completed flows."""
    query = select(ChatThread).where(
        ChatThread.completed_at.is_not(None),
    )
    
    if tenant_id:
        query = query.where(ChatThread.tenant_id == tenant_id)
    
    return list(session.execute(query.order_by(ChatThread.completed_at.desc())).scalars())


def mark_thread_reviewed_by_human(session: Session, thread_id: UUID) -> bool:
    """Mark a thread as reviewed by a human agent."""
    thread = session.get(ChatThread, thread_id)
    if thread:
        thread.human_reviewed_at = datetime.now(UTC)
        session.commit()
        return True
    return False


# --- Flow Version Repository Functions ---


def create_flow_version(
    session: Session,
    *,
    flow_id: UUID,
    definition_snapshot: dict,
    change_description: str | None = None,
    created_by: str | None = None,
) -> FlowVersion:
    """Create a new flow version snapshot."""
    # Get the highest version number for this flow
    latest_version = session.execute(
        select(FlowVersion.version_number)
        .where(FlowVersion.flow_id == flow_id)
        .order_by(desc(FlowVersion.version_number))
    ).scalar()
    
    next_version = (latest_version or 0) + 1
    
    version = FlowVersion(
        flow_id=flow_id,
        version_number=next_version,
        definition_snapshot=definition_snapshot,
        change_description=change_description,
        created_by=created_by,
    )
    session.add(version)
    session.flush()
    
    # Clean up old versions (keep only last 50)
    old_versions = session.execute(
        select(FlowVersion)
        .where(FlowVersion.flow_id == flow_id)
        .order_by(desc(FlowVersion.version_number))
        .offset(50)
    ).scalars().all()
    
    for old_version in old_versions:
        session.delete(old_version)
    
    return version


def get_flow_versions(
    session: Session, 
    flow_id: UUID, 
    limit: int = 20
) -> Sequence[FlowVersion]:
    """Get flow version history."""
    return (
        session.execute(
            select(FlowVersion)
            .where(FlowVersion.flow_id == flow_id)
            .order_by(desc(FlowVersion.version_number))
            .limit(limit)
        )
        .scalars()
        .all()
    )


def get_flow_version_by_number(
    session: Session, 
    flow_id: UUID, 
    version_number: int
) -> FlowVersion | None:
    """Get a specific flow version by number."""
    return session.execute(
        select(FlowVersion)
        .where(
            FlowVersion.flow_id == flow_id,
            FlowVersion.version_number == version_number
        )
    ).scalar_one_or_none()


def update_flow_with_versioning(
    session: Session,
    flow_id: UUID,
    new_definition: dict,
    change_description: str | None = None,
    created_by: str | None = None,
) -> Flow | None:
    """Update flow definition and create version snapshot."""
    flow = get_flow_by_id(session, flow_id)
    if not flow:
        return None
    
    # Create version snapshot of current state before updating
    logger.info(f"Repository: About to create version snapshot for flow {flow_id}, current version: {flow.version}")
    try:
        created_version = create_flow_version(
            session,
            flow_id=flow_id,
            definition_snapshot=flow.definition,
            change_description=change_description,
            created_by=created_by,
        )
        logger.info(f"Repository: Created version snapshot {created_version.version_number} for flow {flow_id}")
    except Exception as e:
        logger.error(f"Repository: CRITICAL ERROR - Failed to create version snapshot for flow {flow_id}: {e}")
        raise
    
    # Update the flow with explicit change detection for JSON fields
    flow.definition = new_definition
    flow.version += 1
    
    # CRITICAL: Force SQLAlchemy to detect the JSON field change
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(flow, "definition")
    
    session.flush()
    
    # CRITICAL: Do NOT commit here - let the calling service handle the commit
    # to avoid nested transaction conflicts
    logger.info(f"Repository: Updated flow {flow_id} in session (waiting for service commit)")
    logger.info(f"Repository: JSON field explicitly marked as modified for flow {flow_id}")
    
    return flow


# Admin-specific repository functions
def get_active_tenants(session: Session) -> list[Tenant]:
    """Get all active tenants with their project configs."""
    return list(session.execute(
        select(Tenant).options(selectinload(Tenant.project_config))
    ).scalars().all())


def get_tenant_by_id(session: Session, tenant_id: UUID) -> Tenant | None:
    """Get a tenant by ID with project config."""
    return session.execute(
        select(Tenant)
        .options(selectinload(Tenant.project_config))
        .where(Tenant.id == tenant_id)
    ).scalar_one_or_none()


def update_tenant(
    session: Session,
    tenant_id: UUID,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    project_description: str | None = None,
    target_audience: str | None = None,
    communication_style: str | None = None,
) -> Tenant | None:
    """Update a tenant and its project config."""
    tenant = get_tenant_by_id(session, tenant_id)
    if not tenant:
        return None
    
    # Update tenant fields
    if first_name is not None:
        tenant.owner_first_name = first_name
    if last_name is not None:
        tenant.owner_last_name = last_name
    if email is not None:
        tenant.owner_email = email
    
    # Update project config
    if tenant.project_config:
        if project_description is not None:
            tenant.project_config.project_description = project_description
        if target_audience is not None:
            tenant.project_config.target_audience = target_audience
        if communication_style is not None:
            tenant.project_config.communication_style = communication_style
    
    session.flush()
    return tenant


def delete_tenant_cascade(session: Session, tenant_id: UUID) -> None:
    """Delete a tenant and all associated data with proper cascading."""
    tenant = get_tenant_by_id(session, tenant_id)
    if not tenant:
        raise ValueError(f"Tenant {tenant_id} not found")
    
    # SQLAlchemy will handle cascading deletes due to the ondelete="CASCADE" 
    # foreign key constraints defined in the models
    session.delete(tenant)
    session.flush()


def get_channel_instances_by_tenant(session: Session, tenant_id: UUID) -> list[ChannelInstance]:
    """Get all channel instances for a tenant."""
    return list(session.execute(
        select(ChannelInstance).where(ChannelInstance.tenant_id == tenant_id)
    ).scalars().all())


def get_flows_by_tenant(session: Session, tenant_id: UUID) -> list[Flow]:
    """Get all flows for a tenant."""
    return list(session.execute(
        select(Flow).where(Flow.tenant_id == tenant_id)
    ).scalars().all())


def update_flow_definition(session: Session, flow_id: UUID, definition: dict) -> Flow | None:
    """Update a flow's definition (for admin JSON editor)."""
    flow = get_flow_by_id(session, flow_id)
    if not flow:
        return None
    
    flow.definition = definition
    flow.version += 1
    
    # Force SQLAlchemy to detect JSON field change
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(flow, "definition")
    
    session.flush()
    return flow
