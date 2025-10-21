"""Flow chat API endpoints using single-tool architecture."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.flow_chat_agent import FlowChatAgent, FlowChatResponse
from app.core.app_context import get_app_context
from app.core.llm import LLMClient
from app.db.models import FlowChatMessage as DBFlowChatMessage
from app.db.session import get_db_session
from app.services.flow_chat_service import FlowChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flows/{flow_id}/chat", tags=["flow-chat"])
router_versions = APIRouter(prefix="/flows/{flow_id}/versions", tags=["flow-versions"])


class SendMessageRequest(BaseModel):
    """Request to send a message to the flow chat."""

    content: str = Field(..., min_length=1, description="Message content")
    simplified_view_enabled: bool = Field(
        default=False, description="Whether the frontend has simplified view enabled"
    )
    active_path: str | None = Field(
        default=None, description="Currently active path in simplified view"
    )


class FlowChatMessage(BaseModel):
    """Single chat message."""

    id: UUID
    flow_id: UUID
    role: str
    content: str
    created_at: str

    @classmethod
    def from_db(cls, db_msg: DBFlowChatMessage) -> FlowChatMessage:
        """Create from database model."""
        return cls(
            id=db_msg.id,
            flow_id=db_msg.flow_id,
            role=db_msg.role.value,
            content=db_msg.content,
            created_at=db_msg.created_at.isoformat(),
        )


@router.get("/messages", response_model=list[FlowChatMessage])
def list_messages(
    flow_id: UUID = Path(...), session: Session = Depends(get_db_session)
) -> list[FlowChatMessage]:
    """List all chat messages for a flow."""
    service = FlowChatService(session, agent=None)  # No agent needed for listing
    messages = service.list_messages(flow_id)
    return [FlowChatMessage.from_db(msg) for msg in messages]


def _build_agent(llm: LLMClient) -> FlowChatAgent:
    """Build the flow chat agent with single-tool architecture."""
    return FlowChatAgent(llm=llm)


@router.post("/send", response_model=FlowChatResponse)
async def send_message(
    request: Request,
    flow_id: UUID = Path(...),
    req: SendMessageRequest | None = None,
    session: Session = Depends(get_db_session),
) -> FlowChatResponse:
    """Send a message to the flow chat and get AI response.

    This endpoint uses single-tool architecture with:
    - Single LLM call
    - Batch actions in one tool
    - Automatic retries
    - Comprehensive error handling
    """
    if req is None:
        raise HTTPException(status_code=400, detail="Content required")

    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    ctx = get_app_context(request.app)
    if ctx.llm is None:
        raise HTTPException(status_code=500, detail="LLM not configured")

    try:
        logger.info(f"Processing chat message for flow {flow_id}: '{req.content[:100]}...'")
        logger.info(
            f"Frontend context - simplified_view: {req.simplified_view_enabled}, "
            f"active_path: {req.active_path}"
        )

        # Create service with agent
        service = FlowChatService(session, agent=_build_agent(ctx.llm))

        # Process with timeout
        try:
            service_response = await asyncio.wait_for(
                service.send_user_message(
                    flow_id,
                    req.content,
                    simplified_view_enabled=req.simplified_view_enabled,
                    active_path=req.active_path,
                ),
                timeout=90.0,  # 90 seconds
            )
        except TimeoutError:
            logger.error(f"Chat request timed out for flow {flow_id}")
            raise HTTPException(status_code=408, detail="Request timed out - please try again")

        logger.info(
            f"Generated {len(service_response.messages)} response messages for flow {flow_id}"
        )
        logger.info(f"Flow was modified: {service_response.flow_was_modified}")

        if service_response.flow_was_modified:
            logger.info(f"Modification summary: {service_response.modification_summary}")

        # Convert to API response format
        return FlowChatResponse(
            messages=[msg.content for msg in service_response.messages],
            flow_was_modified=service_response.flow_was_modified,
            modification_summary=service_response.modification_summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing chat for flow {flow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


# Flow version endpoints
@router_versions.get("", response_model=list[dict])
def list_flow_versions(
    flow_id: UUID = Path(...), limit: int = 20, session: Session = Depends(get_db_session)
) -> list[dict]:
    """List version history for a flow."""
    from app.db.repository import get_flow_versions

    versions = get_flow_versions(session, flow_id, limit=limit)
    return [
        {
            "id": str(v.id),
            "version_number": v.version_number,
            "definition": v.definition,
            "change_description": v.change_description,
            "created_by": v.created_by,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]


@router_versions.get("/{version_number}", response_model=dict)
def get_flow_version(
    flow_id: UUID = Path(...),
    version_number: int = Path(...),
    session: Session = Depends(get_db_session),
) -> dict:
    """Get a specific version of a flow."""
    from app.db.repository import get_flow_version_by_number

    version = get_flow_version_by_number(session, flow_id, version_number)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "definition": version.definition,
        "change_description": version.change_description,
        "created_by": version.created_by,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }
