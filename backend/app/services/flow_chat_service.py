from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.flow_chat_agent import FlowChatAgent
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

    def send_user_message(self, flow_id: UUID, content: str) -> list[FlowChatMessage]:
        if not self.agent:
            raise RuntimeError("agent required to process messages")

        create_flow_chat_message(
            self.session, flow_id=flow_id, role=FlowChatRole.user, content=content
        )
        history = list_flow_chat_messages(self.session, flow_id)

        flow = self.session.get(Flow, flow_id)
        flow_def = flow.definition if flow else {}
        history_dicts = [
            {"role": msg.role.value, "content": msg.content} for msg in history
        ]
        responses = self.agent.process(flow_def, history_dicts)
        saved: list[FlowChatMessage] = []
        for text in responses:
            saved.append(
                create_flow_chat_message(
                    self.session,
                    flow_id=flow_id,
                    role=FlowChatRole.assistant,
                    content=text,
                )
            )
        self.session.commit()
        return saved
