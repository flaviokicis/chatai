"""Clean tool execution service with external action support.

This service handles tool execution with proper feedback loops for external actions.
It ensures the LLM is always aware of the actual results of tool executions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..actions import ActionRegistry, ActionResult
from ..constants import META_NAV_TYPE, META_RESTART
from ..state import FlowContext

logger = logging.getLogger(__name__)


@dataclass
class ToolExecutionResult:
    """Result of tool execution with proper external action feedback.

    Typed result used across runner/responder to avoid dicts and ensure stability.
    """

    # Core execution results
    updates: dict[str, Any] = field(default_factory=dict)
    navigation: dict[str, Any] | None = None
    escalate: bool = False
    terminal: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    # External action results
    external_action_executed: bool = False
    external_action_result: ActionResult | None = None

    @property
    def has_updates(self) -> bool:
        """Check if there are any answer updates."""
        return bool(self.updates)

    @property
    def requires_llm_feedback(self) -> bool:
        """Check if this result requires LLM feedback."""
        return self.external_action_executed and self.external_action_result is not None


class ToolExecutionService:
    """Service for executing flow tools with external action support.

    This service provides clean separation between:
    - Internal actions (navigation, updates) - executed immediately
    - External actions (flow modification, calendar) - executed with feedback
    """

    def __init__(self, action_registry: ActionRegistry):
        """Initialize the tool execution service.

        Args:
            action_registry: Registry of external action executors
        """
        self._action_registry = action_registry

    async def execute_tool(
        self,
        tool_name: str,
        tool_data: dict[str, Any],
        context: FlowContext,
        pending_field: str | None = None,
    ) -> ToolExecutionResult:
        """Execute a tool and process its result.

        Args:
            tool_name: Name of the tool to execute
            tool_data: Tool parameters from LLM
            context: Current flow context
            pending_field: Currently pending field (if any)

        Returns:
            Execution result with updates and potential external action results
        """
        logger.info(f"🔧 Executing tool: {tool_name}")

        try:
            if tool_name == "PerformAction":
                return await self._handle_perform_action(tool_data, context, pending_field)
            
            logger.warning(f"Unknown tool: {tool_name}")
            return ToolExecutionResult()

        except Exception as e:
            logger.error(f"Tool execution failed for {tool_name}: {e}", exc_info=True)
            return ToolExecutionResult(metadata={"error": str(e), "tool_name": tool_name})

    async def _handle_perform_action(
        self,
        tool_data: dict[str, Any],
        context: FlowContext,
        pending_field: str | None,
    ) -> ToolExecutionResult:
        """Handle PerformAction tool with clean action separation."""
        actions = tool_data.get("actions", [])
        result = ToolExecutionResult(metadata={"tool_name": "PerformAction"})

        logger.info(f"Processing {len(actions)} actions: {actions}")

        for action in actions:
            if action == "update":
                self._handle_update_action(tool_data, result, pending_field)
            elif action == "navigate":
                self._handle_navigate_action(tool_data, result)
            elif action == "stay":
                self._handle_stay_action(tool_data, result)
            elif action == "handoff":
                self._handle_handoff_action(tool_data, result)
            elif action == "complete":
                self._handle_complete_action(result)
            elif action == "restart":
                self._handle_restart_action(result)
            elif action == "modify_flow" or action == "update_communication_style":
                await self._handle_external_action(action, tool_data, context, result)
            else:
                logger.warning(f"Unknown action: {action}")

        return result

    def _handle_update_action(
        self, tool_data: dict[str, Any], result: ToolExecutionResult, pending_field: str | None
    ) -> None:
        """Handle answer updates."""
        updates = tool_data.get("updates", {})
        if updates and pending_field:
            result.updates[pending_field] = updates.get(pending_field)
            logger.info(f"Updated field '{pending_field}' with value")

    def _handle_navigate_action(
        self, tool_data: dict[str, Any], result: ToolExecutionResult
    ) -> None:
        """Handle navigation to target node."""
        target_node = tool_data.get("target_node_id")
        if target_node:
            result.navigation = {META_NAV_TYPE: target_node}
            logger.info(f"Navigating to node '{target_node}'")

    def _handle_stay_action(
        self, tool_data: dict[str, Any], result: ToolExecutionResult  
    ) -> None:
        """Handle staying on current node."""
        clarification_reason = tool_data.get("clarification_reason")
        if clarification_reason:
            result.metadata["clarification_reason"] = clarification_reason
        logger.info("Staying on current node")

    def _handle_handoff_action(
        self, tool_data: dict[str, Any], result: ToolExecutionResult
    ) -> None:
        """Handle handoff request."""
        handoff_reason = tool_data.get("handoff_reason")
        result.escalate = True
        result.metadata["handoff_reason"] = handoff_reason
        logger.info(f"Requesting handoff: {handoff_reason}")

    def _handle_complete_action(self, result: ToolExecutionResult) -> None:
        """Handle flow completion."""
        result.terminal = True
        logger.info("Flow completed")

    def _handle_restart_action(self, result: ToolExecutionResult) -> None:
        """Handle flow restart."""
        result.navigation = {META_RESTART: True}
        logger.info("Restarting flow")

    async def _handle_external_action(
        self,
        action_name: str,
        tool_data: dict[str, Any],
        context: FlowContext,
        result: ToolExecutionResult,
    ) -> None:
        """Handle external actions that require feedback.

        Args:
            action_name: Name of the external action
            tool_data: Tool parameters
            context: Flow context
            result: Result object to update
        """
        logger.info("=" * 80)
        logger.info(f"🚀 EXECUTING EXTERNAL ACTION: {action_name}")
        logger.info("=" * 80)

        # Get the appropriate executor
        executor = self._action_registry.get_executor(action_name)
        if not executor:
            logger.error(f"No executor found for action: {action_name}")
            result.external_action_executed = True
            result.external_action_result = ActionResult(
                success=False,
                message=f"❌ Erro interno: ação '{action_name}' não suportada",
                error=f"No executor registered for action: {action_name}",
            )
            return

        # Prepare execution context
        execution_context = {
            "user_id": context.user_id,
            "session_id": context.session_id,
            "tenant_id": context.tenant_id,
            "channel_id": context.channel_id,
            "current_node_id": context.current_node_id,
        }

        # Add flow_id to parameters for flow modification
        if action_name == "modify_flow":
            # context.flow_id is a string like "flow.atendimento_luminarias"
            # We need to get the actual UUID from the database
            # The flow UUID should be available in the FlowRequest metadata
            # For now, we'll need to query it from the tenant_id + flow_id string
            from app.db.session import create_session
            from app.db.repository import get_flows_by_tenant
            
            if context.tenant_id and context.flow_id:
                try:
                    with create_session() as session:
                        flows = get_flows_by_tenant(session, context.tenant_id)
                        matching_flow = next(
                            (f for f in flows if f.flow_id == context.flow_id),
                            None
                        )
                        if matching_flow:
                            tool_data["flow_id"] = str(matching_flow.id)
                            logger.info(f"Resolved flow_id '{context.flow_id}' to UUID {matching_flow.id}")
                        else:
                            logger.error(f"Could not find flow with flow_id='{context.flow_id}' for tenant {context.tenant_id}")
                            result.external_action_executed = True
                            result.external_action_result = ActionResult(
                                success=False,
                                message="A modificação do fluxo falhou porque o sistema não conseguiu identificar qual fluxo modificar. Isso pode ser um erro temporário no banco de dados.",
                                error=f"Flow resolution failed: No flow found with flow_id='{context.flow_id}' for tenant_id={context.tenant_id}",
                                data={
                                    "error_type": "flow_not_found",
                                    "attempted_flow_id": context.flow_id,
                                    "tenant_id": str(context.tenant_id),
                                },
                            )
                            return
                except Exception as e:
                    logger.error(f"Error resolving flow UUID: {e}", exc_info=True)
                    result.external_action_executed = True
                    result.external_action_result = ActionResult(
                        success=False,
                        message="A modificação do fluxo falhou devido a um erro ao acessar o banco de dados. Pode ser uma instabilidade temporária do sistema.",
                        error=f"Database error while resolving flow UUID: {type(e).__name__}: {str(e)}",
                        data={
                            "error_type": "database_error",
                            "exception_type": type(e).__name__,
                        },
                    )
                    return
            else:
                logger.error(f"Missing tenant_id or flow_id in context: tenant_id={context.tenant_id}, flow_id={context.flow_id}")
                result.external_action_executed = True
                result.external_action_result = ActionResult(
                    success=False,
                    message="A modificação do fluxo falhou porque o sistema não tem informações suficientes sobre qual fluxo modificar. Isso indica um problema na configuração interna.",
                    error=f"Missing required context: tenant_id={'present' if context.tenant_id else 'MISSING'}, flow_id={'present' if context.flow_id else 'MISSING'}",
                    data={
                        "error_type": "missing_context",
                        "has_tenant_id": bool(context.tenant_id),
                        "has_flow_id": bool(context.flow_id),
                    },
                )
                return

        try:
            # Execute the external action
            action_result = await executor.execute(tool_data, execution_context)

            result.external_action_executed = True
            result.external_action_result = action_result

            if action_result.is_success:
                logger.info(f"✅ External action '{action_name}' completed successfully")
                
                # Append success confirmation message directly
                success_message = self._build_success_message(action_name, action_result)
                if success_message:
                    # Get existing messages or create new list
                    existing_messages = result.metadata.get("messages", [])
                    # Append success message with delay
                    existing_messages.append({
                        "text": success_message,
                        "delay_ms": 2000
                    })
                    result.metadata["messages"] = existing_messages
                    logger.info(f"📨 Appended success message: {success_message}")
            else:
                logger.error(f"❌ External action '{action_name}' failed: {action_result.error}")
                
                # Append failure message directly
                failure_message = self._build_failure_message(action_name, action_result)
                if failure_message:
                    existing_messages = result.metadata.get("messages", [])
                    existing_messages.append({
                        "text": failure_message,
                        "delay_ms": 2000
                    })
                    result.metadata["messages"] = existing_messages
                    logger.info(f"📨 Appended failure message: {failure_message}")

        except Exception as e:
            logger.error(f"❌ External action '{action_name}' raised exception: {e}", exc_info=True)
            result.external_action_executed = True
            
            # Provide user-friendly message based on action type
            if action_name == "modify_flow":
                user_message = "A modificação do fluxo falhou devido a um erro inesperado durante a execução. Nenhuma mudança foi aplicada."
            else:
                user_message = f"A ação '{action_name}' falhou devido a um erro inesperado."
            
            result.external_action_result = ActionResult(
                success=False,
                message=user_message,
                error=f"Unexpected exception during {action_name} execution: {type(e).__name__}: {str(e)}",
                data={
                    "error_type": "unexpected_exception",
                    "exception_type": type(e).__name__,
                    "action_name": action_name,
                },
            )

    def _build_success_message(self, action_name: str, action_result: ActionResult) -> str | None:
        """Build a user-friendly success message for the completed action.
        
        Args:
            action_name: Name of the action that completed
            action_result: Result from the action execution
            
        Returns:
            Success message in Portuguese, or None if no message needed
        """
        if action_name == "modify_flow":
            # Check if there's a custom message in the result
            if action_result.message:
                return action_result.message
            
            # Get summary from result data
            summary = action_result.data.get("summary", "Modificação aplicada") if action_result.data else "Modificação aplicada"
            return f"✅ Pronto! {summary}"
        
        if action_name == "update_communication_style":
            return "✅ Estilo de comunicação atualizado com sucesso!"
        
        # For other actions, use the result message if available
        return action_result.message if action_result.message else None
    
    def _build_failure_message(self, action_name: str, action_result: ActionResult) -> str | None:
        """Build a user-friendly failure message for the failed action.
        
        Args:
            action_name: Name of the action that failed
            action_result: Result from the action execution
            
        Returns:
            Failure message in Portuguese, or None if no message needed
        """
        # Use the action result's message which should be user-friendly
        if action_result.message:
            return f"❌ {action_result.message}"
        
        # Fallback generic message
        if action_name == "modify_flow":
            return "❌ A modificação do fluxo falhou. Nenhuma mudança foi aplicada."
        if action_name == "update_communication_style":
            return "❌ Não foi possível atualizar o estilo de comunicação."
        
        return f"❌ A ação '{action_name}' falhou."

    # Deprecated legacy handler removed: RequestHumanHandoff
