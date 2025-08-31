from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import NamedTuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.flow_chat_agent import FlowChatAgent


class FlowChatServiceResponse(NamedTuple):
    """Response from flow chat service containing messages and metadata."""
    messages: list[FlowChatMessage]
    flow_was_modified: bool
    modification_summary: str | None = None


from app.db.models import Flow, FlowChatMessage, FlowChatRole
from app.db.repository import (
    create_flow_chat_message,
    get_latest_assistant_message,
    list_flow_chat_messages,
)


class FlowChatService:
    """Service layer for the flow editor chat."""

    def __init__(self, session: Session, agent: FlowChatAgent | None = None) -> None:
        self.session = session
        self.agent = agent

    # message listing
    def list_messages(self, flow_id: UUID) -> Sequence[FlowChatMessage]:
        return list_flow_chat_messages(self.session, flow_id)

    def get_latest_assistant(self, flow_id: UUID) -> FlowChatMessage | None:
        return get_latest_assistant_message(self.session, flow_id)

    async def send_user_message(
        self,
        flow_id: UUID,
        content: str,
        simplified_view_enabled: bool = False,
        active_path: str | None = None
    ) -> FlowChatServiceResponse:
        logger = logging.getLogger(__name__)

        if not self.agent:
            raise RuntimeError("agent required to process messages")

        if not content.strip():
            raise ValueError("message content cannot be empty")

        try:
            # Save user message first
            create_flow_chat_message(
                self.session, flow_id=flow_id, role=FlowChatRole.user, content=content
            )

            # Get flow and history
            flow = self.session.get(Flow, flow_id)
            if not flow:
                raise ValueError(f"Flow {flow_id} not found")

            history = list_flow_chat_messages(self.session, flow_id)
            flow_def = flow.definition if flow else {}
            history_dicts = [
                {"role": msg.role.value, "content": msg.content} for msg in history
            ]

            # Process with agent (pass flow_id and session for persistence)
            try:
                logger.info(f"Calling agent.process for flow {flow_id} with {len(history_dicts)} messages")
                agent_response = await self.agent.process(
                    flow_def,
                    history_dicts,
                    flow_id=flow_id,
                    session=self.session,
                    simplified_view_enabled=simplified_view_enabled,
                    active_path=active_path
                )
                logger.info(f"Agent returned {len(agent_response.messages)} messages, flow_modified={agent_response.flow_was_modified}")
                if agent_response.flow_was_modified:
                    logger.info(f"Flow modifications: {agent_response.modification_summary}")
                for i, resp in enumerate(agent_response.messages):
                    resp_preview = resp[:100] + "..." if len(resp) > 100 else resp
                    logger.info(f"Agent response {i+1}: length={len(resp)}, preview='{resp_preview}'")
            except Exception as e:
                logger.error(f"Agent processing failed for flow {flow_id}: {e!s}")
                # Save error message to chat
                error_msg = create_flow_chat_message(
                    self.session,
                    flow_id=flow_id,
                    role=FlowChatRole.assistant,
                    content=f"❌ Erro ao processar solicitação: {e!s}",
                )
                self.session.commit()
                return FlowChatServiceResponse(
                    messages=[error_msg],
                    flow_was_modified=False,
                    modification_summary=None
                )

            # Save assistant responses
            saved: list[FlowChatMessage] = []
            for text in agent_response.messages:
                saved.append(
                    create_flow_chat_message(
                        self.session,
                        flow_id=flow_id,
                        role=FlowChatRole.assistant,
                        content=text,
                    )
                )

            # CRITICAL DEBUG: Force commit and verify persistence
            logger.info(f"About to commit session for flow {flow_id}")
            self.session.commit()
            logger.info("Session committed successfully")

            # Verify the changes actually persisted
            verification_flow = self.session.get(Flow, flow_id)
            if verification_flow:
                for node in verification_flow.definition.get("nodes", []):
                    if node.get("id") == "q.intensidade_dor":
                        logger.info(f"POST-COMMIT VERIFICATION: q.intensidade_dor allowed_values = {node.get('allowed_values')}")
                        break

            logger.info(f"Successfully processed message for flow {flow_id}, generated {len(saved)} responses")
            return FlowChatServiceResponse(
                messages=saved,
                flow_was_modified=agent_response.flow_was_modified,
                modification_summary=agent_response.modification_summary
            )

        except Exception as e:
            logger.error(f"Failed to process message for flow {flow_id}: {e!s}")
            self.session.rollback()
            raise
