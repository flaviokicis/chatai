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
            # Route to appropriate handler based on tool name
            if tool_name == "PerformAction":
                return await self._handle_perform_action(tool_data, context, pending_field)
            # RequestHumanHandoff tool is deprecated; use PerformAction with action 'handoff'
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
            elif action == "modify_flow":
                # External action - execute with feedback
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
        """Handle navigation actions."""
        target_node_id = tool_data.get("target_node_id")
        if target_node_id:
            result.navigation = {"target_node_id": target_node_id}
            result.metadata[META_NAV_TYPE] = "navigate"
            logger.info(f"Navigation to: {target_node_id}")

    def _handle_stay_action(self, tool_data: dict[str, Any], result: ToolExecutionResult) -> None:
        """Handle stay actions."""
        clarification_reason = tool_data.get("clarification_reason")
        if clarification_reason:
            result.metadata["clarification_reason"] = clarification_reason
        result.metadata[META_NAV_TYPE] = "stay"
        logger.info("Staying on current node")

    def _handle_handoff_action(
        self, tool_data: dict[str, Any], result: ToolExecutionResult
    ) -> None:
        """Handle handoff actions."""
        result.escalate = True
        handoff_reason = tool_data.get("handoff_reason", "user_requested")
        result.metadata["handoff_reason"] = handoff_reason
        logger.info(f"Handoff requested: {handoff_reason}")

    def _handle_complete_action(self, result: ToolExecutionResult) -> None:
        """Handle completion actions."""
        result.terminal = True
        result.metadata["completion_type"] = "normal"
        logger.info("Flow completion requested")

    def _handle_restart_action(self, result: ToolExecutionResult) -> None:
        """Handle restart actions."""
        result.metadata[META_RESTART] = True
        logger.info("Flow restart requested")

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
            tool_data["flow_id"] = context.flow_id

        try:
            # Execute the external action
            action_result = await executor.execute(tool_data, execution_context)

            result.external_action_executed = True
            result.external_action_result = action_result

            if action_result.is_success:
                logger.info(f"✅ External action '{action_name}' completed successfully")
            else:
                logger.error(f"❌ External action '{action_name}' failed: {action_result.error}")

        except Exception as e:
            logger.error(f"❌ External action '{action_name}' raised exception: {e}", exc_info=True)
            result.external_action_executed = True
            result.external_action_result = ActionResult(
                success=False, message=f"❌ Erro interno ao executar {action_name}", error=str(e)
            )

    # Deprecated legacy handler removed: RequestHumanHandoff
