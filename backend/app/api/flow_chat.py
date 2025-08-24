from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.flow_chat_agent import FlowChatAgent, ToolSpec
from app.agents.flow_modification_tools import FLOW_MODIFICATION_TOOLS
from app.core.app_context import get_app_context
from app.db.models import FlowChatRole
from app.db.repository import get_flow_versions, get_flow_version_by_number, update_flow_with_versioning
from app.db.session import get_db_session
from app.services.flow_chat_service import FlowChatService

if TYPE_CHECKING:
    from app.core.llm import LLMClient

router = APIRouter(prefix="/flows/{flow_id}/chat", tags=["flow_chat"])


class SendMessageRequest(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    id: UUID
    role: FlowChatRole
    content: str
    created_at: datetime


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: str | None = None


class FlowVersionResponse(BaseModel):
    id: UUID
    version_number: int
    change_description: str | None
    created_at: datetime
    created_by: str | None


class RestoreVersionRequest(BaseModel):
    version_number: int


def _build_agent(llm: LLMClient) -> FlowChatAgent:
    # Convert flow modification tools to ToolSpec format
    tools: list[ToolSpec] = []
    for tool_config in FLOW_MODIFICATION_TOOLS:
        tools.append(ToolSpec(
            name=tool_config["name"],
            description=tool_config["description"], 
            args_schema=tool_config["args_schema"],
            func=tool_config["func"]
        ))
    return FlowChatAgent(llm=llm, tools=tools)


@router.post("/send", response_model=list[ChatMessageResponse])
def send_message(
    request: Request,
    flow_id: UUID = Path(...),
    req: SendMessageRequest | None = None,
    session: Session = Depends(get_db_session),
) -> list[ChatMessageResponse]:
    logger = logging.getLogger(__name__)
    
    if req is None:
        raise HTTPException(status_code=400, detail="content required")
    
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="message content cannot be empty")
    
    ctx = get_app_context(request.app)  # type: ignore[arg-type]
    if ctx.llm is None:  # pragma: no cover - safeguard
        raise HTTPException(status_code=500, detail="LLM not configured")
    
    try:
        logger.info(f"Processing chat message for flow {flow_id}: '{req.content}'")
        
        service = FlowChatService(session, agent=_build_agent(ctx.llm))
        msgs = service.send_user_message(flow_id, req.content)
        
        logger.info(f"Generated {len(msgs)} response messages for flow {flow_id}")
        for i, msg in enumerate(msgs):
            content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            logger.info(f"Response {i+1}: role={msg.role}, length={len(msg.content)}, preview='{content_preview}'")
        
        return [
            ChatMessageResponse(
                id=m.id, role=m.role, content=m.content, created_at=m.created_at
            )
            for m in msgs
        ]
    except ValueError as e:
        logger.error(f"Validation error in flow chat for {flow_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except RuntimeError as e:
        logger.error(f"Runtime error in flow chat for {flow_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in flow chat for {flow_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error - please try again")


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


# Change history endpoints
router_versions = APIRouter(prefix="/flows/{flow_id}", tags=["flow_versions"])


@router_versions.get("/versions", response_model=list[FlowVersionResponse])
def get_flow_history(
    flow_id: UUID = Path(...), 
    session: Session = Depends(get_db_session),
    limit: int = 20
) -> list[FlowVersionResponse]:
    """Get flow change history."""
    versions = get_flow_versions(session, flow_id, limit)
    return [
        FlowVersionResponse(
            id=v.id,
            version_number=v.version_number,
            change_description=v.change_description,
            created_at=v.created_at,
            created_by=v.created_by
        )
        for v in versions
    ]


@router_versions.post("/restore", response_model=dict)
def restore_flow_version(
    req: RestoreVersionRequest,
    flow_id: UUID = Path(...),
    session: Session = Depends(get_db_session),
) -> dict:
    """Restore flow to a previous version."""
    logger = logging.getLogger(__name__)
    
    try:
        # Get the version to restore
        version = get_flow_version_by_number(session, flow_id, req.version_number)
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")
        
        # Update flow with the snapshot definition
        flow = update_flow_with_versioning(
            session,
            flow_id,
            version.definition_snapshot,
            change_description=f"Restored to version {req.version_number}",
            created_by="system"
        )
        
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        session.commit()
        logger.info(f"Successfully restored flow {flow_id} to version {req.version_number}")
        
        return {
            "message": f"Flow restored to version {req.version_number}",
            "current_version": flow.version
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restore flow {flow_id} to version {req.version_number}: {str(e)}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Failed to restore version")
