"""Database operations handler for WhatsApp webhook processing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException

from app.db.models import Flow as FlowModel
from app.db.repository import (
    find_channel_instance_by_identifier,
    get_flows_by_channel_instance,
    get_or_create_contact,
    get_or_create_thread,
)
from app.services.tenant_config_service import TenantConfigService
from app.whatsapp.types import ConversationSetup

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.db.models import ChannelInstance

logger = logging.getLogger(__name__)


class WebhookDatabaseHandler:
    """
    Handles all database operations for WhatsApp webhook processing.

    Encapsulates tenant resolution, channel setup, contact/thread management,
    and flow selection in clean, transactional operations.
    """

    def __init__(self, session: Session):
        self.session = session
        self.tenant_service = TenantConfigService(session)

    def setup_conversation(self, sender_number: str, receiver_number: str) -> ConversationSetup:
        try:
            project_context = self.tenant_service.get_project_context_by_channel_identifier(
                receiver_number
            )

            if not project_context:
                raise HTTPException(
                    status_code=422,
                    detail=f"No tenant configuration found for WhatsApp number: {receiver_number}",
                )

            tenant_id = project_context.tenant_id
            logger.info("Found tenant %s for channel %s", tenant_id, receiver_number)

            channel_instance = find_channel_instance_by_identifier(self.session, receiver_number)
            if not channel_instance:
                raise HTTPException(
                    status_code=422,
                    detail=f"No channel instance found for number {receiver_number}",
                )

            contact = get_or_create_contact(
                self.session,
                tenant_id,
                external_id=sender_number,
                phone_number=sender_number.replace("whatsapp:", ""),
                display_name=None,
            )
            if not contact or not contact.id:
                raise HTTPException(status_code=500, detail="Failed to create/retrieve contact")

            thread = get_or_create_thread(
                self.session,
                tenant_id=tenant_id,
                channel_instance_id=channel_instance.id,
                contact_id=contact.id,
                flow_id=None,
            )
            if not thread or not thread.id:
                raise HTTPException(status_code=500, detail="Failed to create/retrieve thread")

            selected_flow = self._select_active_flow(channel_instance, tenant_id)
            if not selected_flow or not selected_flow.flow_id or not selected_flow.name:
                raise HTTPException(
                    status_code=422, detail=f"No active flows found for channel {receiver_number}"
                )

            self.session.commit()

            logger.info(
                "Using flow '%s' (flow_id='%s') for tenant %s",
                selected_flow.name,
                selected_flow.flow_id,
                tenant_id,
            )

            flow_definition = selected_flow.definition
            if not flow_definition:
                raise HTTPException(status_code=500, detail="Flow definition is empty")

            return ConversationSetup(
                tenant_id=tenant_id,
                channel_instance_id=channel_instance.id,
                thread_id=thread.id,
                contact_id=contact.id,
                flow_id=selected_flow.flow_id,
                flow_name=selected_flow.name,
                selected_flow_id=selected_flow.flow_id,
                flow_definition=flow_definition,
                project_context=project_context,
            )

        except HTTPException:
            self.session.rollback()
            raise
        except Exception as e:
            logger.error("Failed to setup conversation: %s", e)
            self.session.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    def _select_active_flow(
        self, channel_instance: ChannelInstance, tenant_id: UUID
    ) -> FlowModel | None:
        """Select the first active flow for the given channel instance."""
        if not channel_instance.id:
            logger.error("Channel instance has no ID")
            return None
            
        flows = get_flows_by_channel_instance(self.session, channel_instance.id)
        if not flows:
            logger.error(
                "No flows found for channel instance %s (tenant %s)", channel_instance.id, tenant_id
            )
            return None

        active_flows = [f for f in flows if f.is_active]
        if not active_flows:
            logger.error(
                "No active flows found for channel instance %s (tenant %s)",
                channel_instance.id,
                tenant_id,
            )
            return None

        return active_flows[0]
