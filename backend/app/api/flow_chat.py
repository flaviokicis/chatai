from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.flow_chat_agent import FlowChatAgent, ToolSpec
from app.core.app_context import get_app_context
from app.core.llm import LLMClient
from app.db.models import FlowChatRole
from app.db.session import get_db_session
from app.services.flow_chat_service import FlowChatService

router = APIRouter(prefix="/flows/{flow_id}/chat", tags=["flow_chat"])


class SendMessageRequest(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    id: UUID
    role: FlowChatRole
    content: str
    created_at: datetime


def _build_agent(llm: LLMClient) -> FlowChatAgent:
    # No concrete tools yet; placeholder for future expansion
    tools: List[ToolSpec] = []
    return FlowChatAgent(llm=llm, tools=tools)


@router.post("/send", response_model=list[ChatMessageResponse])
def send_message(
    flow_id: UUID = Path(...),
    req: SendMessageRequest | None = None,
    session: Session = Depends(get_db_session),
) -> list[ChatMessageResponse]:
    if req is None:
        raise HTTPException(status_code=400, detail="content required")
    ctx = get_app_context()
    if ctx.llm is None:  # pragma: no cover - safeguard
        raise HTTPException(status_code=500, detail="LLM not configured")
    service = FlowChatService(session, agent=_build_agent(ctx.llm))
    msgs = service.send_user_message(flow_id, req.content)
    return [
        ChatMessageResponse(
            id=m.id, role=m.role, content=m.content, created_at=m.created_at
        )
        for m in msgs
    ]


@router.get("/messages", response_model=list[ChatMessageResponse])
def list_messages(
    flow_id: UUID = Path(...), session: Session = Depends(get_db_session)
) -> list[ChatMessageResponse]:
    service = FlowChatService(session)
    msgs = service.list_messages(flow_id)
    return [
        ChatMessageResponse(
            id=m.id, role=m.role, content=m.content, created_at=m.created_at
        )
        for m in msgs
    ]


@router.get("/receive", response_model=ChatMessageResponse | None)
def receive_latest(
    flow_id: UUID = Path(...), session: Session = Depends(get_db_session)
) -> ChatMessageResponse | None:
    service = FlowChatService(session)
    m = service.get_latest_assistant(flow_id)
    if not m:
        return None
    return ChatMessageResponse(
        id=m.id, role=m.role, content=m.content, created_at=m.created_at
    )
