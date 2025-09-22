"""Communication style update action executor.

This module implements the communication style update action that can be called by admin users.
It provides a clean interface between the LLM and the tenant project configuration service.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.db.session import create_session
from app.db.repository import update_tenant_project_config, get_tenant_by_id
from app.services.admin_phone_service import AdminPhoneService

from .base import ActionExecutor, ActionResult

logger = logging.getLogger(__name__)


class CommunicationStyleExecutor(ActionExecutor):
    """Executes communication style update actions for admin users.

    This executor provides a clean interface for the LLM to update communication
    style instructions while ensuring proper error handling and admin validation.
    """

    @property
    def action_name(self) -> str:
        """Action identifier."""
        return "update_communication_style"

    async def execute(self, parameters: dict[str, Any], context: dict[str, Any]) -> ActionResult:
        """Execute the communication style update action.

        Args:
            parameters: Should contain 'communication_style_instruction'
            context: Execution context with 'user_id', 'tenant_id', etc.

        Returns:
            ActionResult with success/failure status and user message
        """
        try:
            # Extract parameters
            instruction = parameters.get("communication_style_instruction")
            if not instruction:
                return ActionResult(
                    success=False,
                    message="Erro: Instrução de estilo de comunicação não fornecida.",
                    details={"error": "Missing communication_style_instruction"},
                )

            # Extract context - handle both dict and FlowContext objects
            if hasattr(context, 'user_id'):
                # FlowContext object
                user_id = context.user_id
                tenant_id = context.tenant_id
            else:
                # Dict context from tool executor
                user_id = context.get("user_id")
                tenant_id = context.get("tenant_id")

            if not user_id or not tenant_id:
                return ActionResult(
                    success=False,
                    message="Erro: Informações de contexto insuficientes.",
                    details={"error": "Missing user_id or tenant_id"},
                )

            # Convert tenant_id to UUID if it's a string
            if isinstance(tenant_id, str):
                try:
                    tenant_id = UUID(tenant_id)
                except ValueError:
                    return ActionResult(
                        success=False,
                        message="Erro: ID do inquilino inválido.",
                        details={"error": "Invalid tenant_id format"},
                    )

            # Check if user is admin
            with create_session() as session:
                admin_service = AdminPhoneService(session)
                is_admin = admin_service.is_admin_phone(
                    phone_number=user_id,
                    tenant_id=tenant_id
                )

                if not is_admin:
                    logger.warning(
                        f"Non-admin user {user_id} attempted to update communication style for tenant {tenant_id}"
                    )
                    return ActionResult(
                        success=False,
                        message="Desculpe, apenas administradores podem alterar o estilo de comunicação.",
                        details={"error": "User is not admin"},
                    )

                # Get current tenant and project config
                tenant = get_tenant_by_id(session, tenant_id)
                if not tenant:
                    return ActionResult(
                        success=False,
                        message="Erro: Inquilino não encontrado.",
                        details={"error": "Tenant not found"},
                    )

                # Get current communication style
                current_style = ""
                if tenant.project_config and tenant.project_config.communication_style:
                    current_style = tenant.project_config.communication_style

                # Append the new instruction to the current style
                # Add a separator if there's existing content
                if current_style:
                    updated_style = f"{current_style}\n\n{instruction}"
                else:
                    updated_style = instruction

                # Update the project config
                updated_tenant = update_tenant_project_config(
                    session,
                    tenant_id=tenant_id,
                    project_description=tenant.project_config.project_description if tenant.project_config else None,
                    target_audience=tenant.project_config.target_audience if tenant.project_config else None,
                    communication_style=updated_style,
                )

                session.commit()

                if updated_tenant:
                    logger.info(
                        f"Admin {user_id} updated communication style for tenant {tenant_id}"
                    )
                    return ActionResult(
                        success=True,
                        message="✅ Estilo de comunicação atualizado com sucesso! As próximas mensagens seguirão as novas instruções.",
                        details={
                            "instruction_added": instruction,
                            "tenant_id": str(tenant_id),
                        },
                    )
                else:
                    return ActionResult(
                        success=False,
                        message="Erro ao atualizar o estilo de comunicação.",
                        details={"error": "Failed to update tenant config"},
                    )

        except Exception as e:
            logger.error(f"Unexpected error in communication style update: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Erro inesperado ao atualizar o estilo de comunicação.",
                details={"error": str(e)},
            )
