"""Flow modification action executor.

This module implements the flow modification action that can be called by the LLM.
It provides a clean interface between the LLM and the flow modification service.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.agents.flow_chat_agent import FlowChatAgent
from app.core.llm import LLMClient
from app.db.session import create_session
from app.services.flow_chat_service import FlowChatService

from .base import ActionExecutor, ActionResult

logger = logging.getLogger(__name__)


class FlowModificationExecutor(ActionExecutor):
    """Executes flow modification actions through the FlowChatService.

    This executor provides a clean interface for the LLM to modify flows
    while ensuring proper error handling and user feedback.
    """

    def __init__(self, llm_client: LLMClient):
        """Initialize the flow modification executor.

        Args:
            llm_client: LLM client for the flow chat agent
        """
        self._llm_client = llm_client

    @property
    def action_name(self) -> str:
        """Action identifier."""
        return "modify_flow"

    async def execute(self, parameters: dict[str, Any], context: dict[str, Any]) -> ActionResult:
        """Execute flow modification.

        Args:
            parameters: Must contain 'flow_modification_instruction' and 'flow_id'
            context: Must contain execution context

        Returns:
            ActionResult with modification outcome
        """
        try:
            # Extract required parameters
            instruction = parameters.get("flow_modification_instruction")
            if not instruction:
                return ActionResult(
                    success=False,
                    message="❌ Erro interno: instrução de modificação não fornecida",
                    error="Missing flow_modification_instruction parameter",
                )

            flow_id_raw = parameters.get("flow_id")
            if not flow_id_raw:
                return ActionResult(
                    success=False,
                    message="❌ Erro interno: ID do fluxo não fornecido",
                    error="Missing flow_id parameter",
                )

            # Convert flow_id to UUID
            try:
                flow_id = UUID(flow_id_raw) if isinstance(flow_id_raw, str) else flow_id_raw
            except (ValueError, TypeError) as e:
                return ActionResult(
                    success=False,
                    message="❌ Erro interno: ID do fluxo inválido",
                    error=f"Invalid flow_id: {e}",
                )

            logger.info("=" * 80)
            logger.info("🔧 FLOW MODIFICATION EXECUTOR: Starting execution")
            logger.info("=" * 80)
            logger.info(f"Flow ID: {flow_id}")
            logger.info(
                f"Instruction: {instruction[:200]}..."
                if len(instruction) > 200
                else f"Instruction: {instruction}"
            )
            logger.info("=" * 80)

            # Execute modification using FlowChatService
            result = await self._execute_modification(flow_id, instruction)

            if result.success:
                logger.info("✅ Flow modification completed successfully")
                return ActionResult(
                    success=True,
                    message="✅ Fluxo modificado com sucesso! As alterações foram aplicadas.",
                    data={"summary": result.data.get("summary") if result.data else None},
                )
            logger.error(f"❌ Flow modification failed: {result.error}")
            return ActionResult(
                success=False,
                message=f"❌ Falha ao modificar o fluxo: {result.error or 'Erro desconhecido'}",
                error=result.error,
            )

        except Exception as e:
            logger.error("❌ Unexpected error in flow modification executor", exc_info=True)
            return ActionResult(
                success=False,
                message="❌ Erro interno inesperado ao modificar o fluxo",
                error=str(e),
            )

    async def _execute_modification(self, flow_id: UUID, instruction: str) -> ActionResult:
        """Execute the actual flow modification.

        Args:
            flow_id: ID of the flow to modify
            instruction: Modification instruction

        Returns:
            ActionResult with execution outcome
        """
        try:
            # Create agent and service in a new event loop context
            agent = FlowChatAgent(llm=self._llm_client)

            with create_session() as session:
                service = FlowChatService(session, agent=agent)

                # Execute the modification
                response = await service.send_user_message(flow_id, instruction)

                if response.flow_was_modified:
                    return ActionResult(
                        success=True,
                        message="Flow modified successfully",
                        data={"summary": response.modification_summary},
                    )
                return ActionResult(
                    success=False,
                    message="No modifications were made",
                    error="FlowChatService returned flow_was_modified=False",
                )

        except Exception as e:
            logger.error(f"Error executing flow modification: {e}", exc_info=True)
            return ActionResult(
                success=False, message="Failed to execute modification", error=str(e)
            )
