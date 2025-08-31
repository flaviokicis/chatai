"""Tool for live flow modification during conversations by admin users."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.flow_chat_agent import FlowChatAgent, ToolSpec
from app.agents.flow_modification_tools import FLOW_MODIFICATION_TOOLS
from app.core.llm import LLMClient
from app.db.models import Flow
from app.db.repository import get_flow_by_id, update_flow_with_versioning
from app.services.flow_chat_service import FlowChatService

logger = logging.getLogger(__name__)


class LiveFlowModificationRequest(BaseModel):
    """Request to modify the flow live during conversation."""
    
    instruction: str = Field(
        description="User instruction for how to modify the flow (e.g., 'you should ask about nail type first')"
    )
    reason: Literal["admin_instruction"] = Field(
        default="admin_instruction",
        description="Reason for the modification"
    )


class LiveFlowModificationResult(BaseModel):
    """Result of live flow modification."""
    
    success: bool = Field(description="Whether the modification was successful")
    message: str = Field(description="Message to show to the admin user")
    flow_modified: bool = Field(description="Whether the flow was actually modified")
    modification_summary: str | None = Field(default=None, description="Summary of what was changed")


async def modify_flow_live(
    instruction: str,
    flow_id: UUID,
    session: Session,
    llm: LLMClient,
    project_context: dict[str, Any] | None = None
) -> LiveFlowModificationResult:
    """
    Modify a flow live using the same chat-to-flow LLM system.
    
    Args:
        instruction: Admin instruction for how to modify the flow
        flow_id: ID of the flow to modify
        session: Database session
        llm: LLM client for processing the modification
        project_context: Optional project context for the modification
        
    Returns:
        Result of the modification attempt
    """
    try:
        logger.info(f"Processing live flow modification for flow {flow_id}: '{instruction}'")
        
        # Get the current flow
        flow = session.get(Flow, flow_id)
        if not flow:
            return LiveFlowModificationResult(
                success=False,
                message="Erro: Fluxo não encontrado.",
                flow_modified=False
            )
        
        # Build the flow chat agent with modification tools
        tools: list[ToolSpec] = []
        for tool_config in FLOW_MODIFICATION_TOOLS:
            tools.append(ToolSpec(
                name=tool_config["name"],
                description=tool_config["description"],
                args_schema=tool_config["args_schema"],
                func=tool_config["func"]
            ))
        
        agent = FlowChatAgent(llm=llm, tools=tools)
        
        # Create a conversation history with the instruction
        history = [
            {"role": "user", "content": instruction}
        ]
        
        # Process the instruction using the flow chat agent
        try:
            agent_response = await asyncio.wait_for(
                agent.process(
                    flow.definition,
                    history,
                    flow_id=flow_id,
                    session=session,
                    simplified_view_enabled=False,
                    active_path=None
                ),
                timeout=60.0  # 1 minute timeout for live modifications
            )
            
            if agent_response.flow_was_modified:
                logger.info(f"Flow {flow_id} was modified live: {agent_response.modification_summary}")
                return LiveFlowModificationResult(
                    success=True,
                    message="Ah, ok, anotado. Da próxima vez irei fazer conforme sua instrução.",
                    flow_modified=True,
                    modification_summary=agent_response.modification_summary
                )
            else:
                # Agent understood but didn't make changes
                last_message = agent_response.messages[-1] if agent_response.messages else "Não foi possível processar a instrução."
                return LiveFlowModificationResult(
                    success=True,
                    message=f"Entendi sua instrução, mas não foi necessário fazer mudanças no fluxo. {last_message}",
                    flow_modified=False
                )
                
        except asyncio.TimeoutError:
            logger.error(f"Live flow modification timed out for flow {flow_id}")
            return LiveFlowModificationResult(
                success=False,
                message="Desculpe, a modificação demorou muito para processar. Tente novamente.",
                flow_modified=False
            )
            
    except Exception as e:
        logger.error(f"Error in live flow modification for flow {flow_id}: {e}", exc_info=True)
        return LiveFlowModificationResult(
            success=False,
            message="Desculpe, ocorreu um erro ao processar sua instrução. Tente novamente.",
            flow_modified=False
        )


def live_flow_modification_tool_func(
    instruction: str,
    flow_id: UUID,
    session: Session,
    llm: LLMClient,
    project_context: dict[str, Any] | None = None
) -> str:
    """
    Synchronous wrapper for the live flow modification tool.
    
    This is used by the flow processing system which expects synchronous tool functions.
    """
    try:
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                modify_flow_live(instruction, flow_id, session, llm, project_context)
            )
            return result.message
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error in live flow modification tool: {e}", exc_info=True)
        return "Desculpe, ocorreu um erro ao processar sua instrução. Tente novamente."
