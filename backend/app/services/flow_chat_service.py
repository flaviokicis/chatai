"""Flow chat service using v2 single-tool architecture."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import NamedTuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.flow_chat_agent_v2 import FlowChatAgentV2
from app.db.models import Flow, FlowChatMessage, FlowChatRole
from app.db.repository import (
    create_flow_chat_message,
    get_latest_assistant_message,
    list_flow_chat_messages,
)

logger = logging.getLogger(__name__)


class FlowChatServiceResponse(NamedTuple):
    """Response from flow chat service."""
    
    messages: list[FlowChatMessage]
    flow_was_modified: bool
    modification_summary: str | None = None


class FlowChatService:
    """Service layer for flow chat using v2 single-tool architecture.
    
    This service coordinates between the UI, database, and the v2 agent
    that uses a single LLM call with batch actions.
    """
    
    def __init__(self, session: Session, agent: FlowChatAgentV2):
        """Initialize the service with a database session and v2 agent."""
        self.session = session
        self.agent = agent
    
    def list_messages(self, flow_id: UUID) -> Sequence[FlowChatMessage]:
        """List all chat messages for a flow."""
        return list_flow_chat_messages(self.session, flow_id)
    
    def get_latest_assistant(self, flow_id: UUID) -> FlowChatMessage | None:
        """Get the latest assistant message for a flow."""
        return get_latest_assistant_message(self.session, flow_id)
    
    async def send_user_message(
        self,
        flow_id: UUID,
        content: str,
        simplified_view_enabled: bool = False,
        active_path: str | None = None
    ) -> FlowChatServiceResponse:
        """Process a user message and modify the flow as needed.
        
        Args:
            flow_id: UUID of the flow to modify
            content: User's message content
            simplified_view_enabled: Whether simplified view is active
            active_path: Currently active path in simplified view
            
        Returns:
            FlowChatServiceResponse with messages and modification status
        """
        if not content.strip():
            raise ValueError("Message content cannot be empty")
        
        logger.info(
            f"Processing message for flow {flow_id}: '{content[:100]}...', "
            f"simplified={simplified_view_enabled}, path={active_path}"
        )
        
        try:
            # Save user message to database
            create_flow_chat_message(
                self.session,
                flow_id=flow_id,
                role=FlowChatRole.user,
                content=content
            )
            
            # Get flow definition and history
            flow = self.session.get(Flow, flow_id)
            if not flow:
                raise ValueError(f"Flow {flow_id} not found")
            
            flow_def = flow.definition
            history = list_flow_chat_messages(self.session, flow_id)
            history_dicts = [
                {"role": msg.role.value, "content": msg.content}
                for msg in history
            ]
            
            # Process with v2 agent
            logger.info(f"Calling v2 agent with {len(history_dicts)} history messages")
            
            agent_response = await self.agent.process(
                flow=flow_def,
                history=history_dicts,
                flow_id=flow_id,
                session=self.session,
                simplified_view_enabled=simplified_view_enabled,
                active_path=active_path
            )
            
            logger.info(
                f"Agent returned: messages={len(agent_response.messages)}, "
                f"modified={agent_response.flow_was_modified}"
            )
            
            if agent_response.flow_was_modified:
                logger.info(f"Modifications: {agent_response.modification_summary}")
            
            # Save assistant responses
            saved_messages = []
            for message in agent_response.messages:
                saved_msg = create_flow_chat_message(
                    self.session,
                    flow_id=flow_id,
                    role=FlowChatRole.assistant,
                    content=message
                )
                saved_messages.append(saved_msg)
            
            # Commit the transaction
            self.session.commit()
            logger.info(f"Successfully committed {len(saved_messages)} messages")
            
            # Verify persistence in production for debugging
            if agent_response.flow_was_modified:
                verification_flow = self.session.get(Flow, flow_id)
                if verification_flow:
                    node_count = len(verification_flow.definition.get("nodes", []))
                    edge_count = len(verification_flow.definition.get("edges", []))
                    logger.info(
                        f"Verification: Flow {flow_id} now has "
                        f"{node_count} nodes and {edge_count} edges"
                    )
            
            return FlowChatServiceResponse(
                messages=saved_messages,
                flow_was_modified=agent_response.flow_was_modified,
                modification_summary=agent_response.modification_summary
            )
            
        except Exception as e:
            logger.error(f"Failed to process message for flow {flow_id}: {e}", exc_info=True)
            
            # Rollback the transaction
            self.session.rollback()
            
            # Save error message
            try:
                error_msg = create_flow_chat_message(
                    self.session,
                    flow_id=flow_id,
                    role=FlowChatRole.assistant,
                    content="❌ Desculpe, ocorreu um erro ao processar sua solicitação. Por favor, tente novamente."
                )
                self.session.commit()
                
                return FlowChatServiceResponse(
                    messages=[error_msg],
                    flow_was_modified=False,
                    modification_summary=None
                )
            except Exception as save_error:
                logger.error(f"Failed to save error message: {save_error}")
                raise