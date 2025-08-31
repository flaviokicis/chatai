"""Database operations handler for WhatsApp webhook processing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from app.db.models import Flow as FlowModel
from app.db.repository import (
    find_channel_instance_by_identifier,
    get_flows_by_channel_instance,
    get_or_create_contact,
    get_or_create_thread,
)
from app.services.tenant_config_service import TenantConfigService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.db.models import ChannelInstance, Contact, Thread
    from app.services.tenant_config_service import ProjectContext

logger = logging.getLogger(__name__)


@dataclass
class ConversationSetup:
    """Complete conversation setup data from database operations."""

    tenant_id: UUID
    project_context: ProjectContext
    channel_instance: ChannelInstance
    contact: Contact
    thread: Thread
    selected_flow: FlowModel

    # Extracted IDs and data for use after session closes
    thread_id: UUID
    contact_id: UUID
    channel_instance_id: UUID
    selected_flow_id: UUID
    flow_definition: dict[str, Any]
    flow_name: str
    flow_id: str


class WebhookDatabaseHandler:
    """
    Handles all database operations for WhatsApp webhook processing.
    
    Encapsulates tenant resolution, channel setup, contact/thread management,
    and flow selection in clean, transactional operations.
    """

    def __init__(self, session: Session):
        self.session = session
        self.tenant_service = TenantConfigService(session)

    def setup_conversation(
        self,
        sender_number: str,
        receiver_number: str
    ) -> ConversationSetup | None:
        """
        Set up complete conversation context from database.
        
        Handles:
        1. Tenant configuration resolution
        2. Channel instance lookup  
        3. Contact/thread creation or retrieval
        4. Active flow selection
        
        Args:
            sender_number: WhatsApp sender number (with whatsapp: prefix)
            receiver_number: WhatsApp receiver number (with whatsapp: prefix)
            
        Returns:
            ConversationSetup with all required data, or None if setup failed
        """
        try:
            # Step 1: Get tenant configuration
            project_context = self.tenant_service.get_project_context_by_channel_identifier(
                receiver_number
            )

            if not project_context:
                logger.warning("No tenant configuration found for WhatsApp number: %s", receiver_number)
                return None

            tenant_id = project_context.tenant_id
            logger.info("Found tenant %s for channel %s", tenant_id, receiver_number)

            # Step 2: Get channel instance
            channel_instance = find_channel_instance_by_identifier(self.session, receiver_number)
            if not channel_instance:
                logger.error("No channel instance found for number %s (tenant %s)",
                           receiver_number, tenant_id)
                return None

            # Step 3: Ensure contact/thread exist
            contact = get_or_create_contact(
                self.session,
                tenant_id,
                external_id=sender_number,
                phone_number=sender_number.replace("whatsapp:", ""),
                display_name=None,
            )

            thread = get_or_create_thread(
                self.session,
                tenant_id=tenant_id,
                channel_instance_id=channel_instance.id,
                contact_id=contact.id,
                flow_id=None,
            )

            # Step 4: Get and select active flow
            selected_flow = self._select_active_flow(channel_instance, tenant_id)
            if not selected_flow:
                return None

            # Commit all database changes
            self.session.commit()

            logger.info("Using flow '%s' (flow_id='%s') for tenant %s",
                       selected_flow.name, selected_flow.flow_id, tenant_id)

            # Extract flow definition while session is active
            flow_definition = selected_flow.definition
            if isinstance(flow_definition, dict) and flow_definition.get("schema_version") != "v2":
                flow_definition["schema_version"] = "v2"

            return ConversationSetup(
                tenant_id=tenant_id,
                project_context=project_context,
                channel_instance=channel_instance,
                contact=contact,
                thread=thread,
                selected_flow=selected_flow,
                # Extract IDs and data for use after session closes
                thread_id=thread.id,
                contact_id=contact.id,
                channel_instance_id=channel_instance.id,
                selected_flow_id=selected_flow.id,
                flow_definition=flow_definition,
                flow_name=selected_flow.name,
                flow_id=selected_flow.flow_id,
            )

        except Exception as e:
            logger.error("Failed to setup conversation for tenant lookup: %s", e)
            self.session.rollback()
            return None

    def _select_active_flow(
        self,
        channel_instance: ChannelInstance,
        tenant_id: UUID
    ) -> FlowModel | None:
        """
        Select the first active flow for the given channel instance.
        
        Args:
            channel_instance: Channel instance to find flows for
            tenant_id: Tenant ID for logging
            
        Returns:
            Selected active flow or None if no active flows found
        """
        flows = get_flows_by_channel_instance(self.session, channel_instance.id)
        if not flows:
            logger.error("No flows found for channel instance %s (tenant %s)",
                        channel_instance.id, tenant_id)
            return None

        active_flows = [f for f in flows if f.is_active]
        if not active_flows:
            logger.error("No active flows found for channel instance %s (tenant %s)",
                        channel_instance.id, tenant_id)
            return None

        return active_flows[0]
