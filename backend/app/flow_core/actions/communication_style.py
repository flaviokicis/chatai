"""Communication style update action executor.

This module implements the communication style update action that can be called by admin users.
It provides a clean interface between the LLM and the tenant project configuration service.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.db.repository import get_tenant_by_id, update_tenant_project_config
from app.db.session import create_session
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
            parameters: Should contain 'updated_communication_style'
            context: Execution context with 'user_id', 'tenant_id', etc.

        Returns:
            ActionResult with success/failure status and user message
        """
        try:
            new_style = parameters.get("updated_communication_style")
            if not new_style:
                return ActionResult(
                    success=False,
                    message="Erro: Novo estilo de comunicação não fornecido.",
                    error="Missing updated_communication_style",
                )

            if hasattr(context, "user_id"):
                user_id = context.user_id
                tenant_id = context.tenant_id  # type: ignore[attr-defined]
            else:
                user_id = context.get("user_id")
                tenant_id = context.get("tenant_id")

            if not user_id or not tenant_id:
                return ActionResult(
                    success=False,
                    message="Erro: Informações de contexto insuficientes.",
                    error="Missing user_id or tenant_id",
                )

            if isinstance(tenant_id, str):
                try:
                    tenant_id = UUID(tenant_id)
                except ValueError:
                    return ActionResult(
                        success=False,
                        message="Erro: ID do inquilino inválido.",
                        error="Invalid tenant_id format",
                    )

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
                        error="User is not admin",
                    )

                tenant = get_tenant_by_id(session, tenant_id)
                if not tenant:
                    return ActionResult(
                        success=False,
                        message="Erro: Inquilino não encontrado.",
                        error="Tenant not found",
                    )

                updated_tenant = update_tenant_project_config(
                    session,
                    tenant_id=tenant_id,
                    project_description=tenant.project_config.project_description if tenant.project_config else None,
                    target_audience=tenant.project_config.target_audience if tenant.project_config else None,
                    communication_style=new_style,
                )

                session.commit()

                if updated_tenant:
                    logger.info(
                        f"Admin {user_id} updated communication style for tenant {tenant_id}"
                    )
                    return ActionResult(
                        success=True,
                        message="✅ Estilo de comunicação atualizado com sucesso! As próximas mensagens seguirão o novo estilo.",
                        data={
                            "new_style": new_style[:200] + "..." if len(new_style) > 200 else new_style,
                            "tenant_id": str(tenant_id),
                        },
                    )
                return ActionResult(
                    success=False,
                    message="Erro ao atualizar o estilo de comunicação.",
                    error="Failed to update tenant config",
                )

        except Exception as e:
            logger.error(f"Unexpected error in communication style update: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Erro inesperado ao atualizar o estilo de comunicação.",
                error=str(e),
            )
