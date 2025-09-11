"""Tool execution service for processing flow tool responses.

This service handles the execution and processing of tool responses,
updating the flow context and determining navigation actions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..state import FlowContext

from ..constants import (
    CLARIFICATION_NEEDS_EXPLANATION,
    DEFAULT_CLARIFICATION_COUNT,
    DEFAULT_PATH_CORRECTIONS,
    META_NAV_TYPE,
    META_REASONING,
    META_RESTART,
)
from ..types import (
    AnswersDict,
    MetadataDict,
    PerformActionCall,
    ToolExecutionError,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolExecutionResult:
    """Result of executing a flow tool."""

    updates: AnswersDict = field(default_factory=dict)
    navigation: str | None = None
    escalate: bool = False
    terminal: bool = False
    metadata: MetadataDict = field(default_factory=dict)

    @property
    def requires_navigation(self) -> bool:
        """Check if this result requires navigation to a different node."""
        return self.navigation is not None

    @property
    def has_updates(self) -> bool:
        """Check if there are any answer updates."""
        return bool(self.updates)


class ToolExecutionService:
    """Service for executing flow tools and processing their results."""

    def execute_tool(
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
            Execution result with updates and navigation info
            
        Raises:
            ToolExecutionError: If tool execution fails
        """
        logger.debug(f"Executing tool {tool_name} with data: {tool_data}")

        try:
            # Route to appropriate handler based on tool name
            if tool_name == "ModifyFlowLive":
                return self._handle_modify_flow_live(tool_data, context)
            if tool_name == "PerformAction":
                return self._handle_perform_action(tool_data, context, pending_field)
            if tool_name == "RequestHumanHandoff":
                return ToolExecutionResult(
                    updates={},
                    navigation=None,
                    escalate=True,
                    terminal=False,
                    metadata={"reason": tool_data.get("reason", "user_requested")},
                )
            logger.warning(f"Unknown tool: {tool_name}")
            return self._create_empty_result()

        except Exception as e:
            logger.exception(f"Tool execution failed for {tool_name}: {e}")
            raise ToolExecutionError(
                tool_name=tool_name,
                message=f"Failed to execute {tool_name}: {e}",
                original_error=e,
            )


    def _handle_perform_action(
        self,
        tool_data: dict[str, Any],
        context: FlowContext,
        pending_field: str | None,
    ) -> ToolExecutionResult:
        """Handle PerformAction unified tool with sequential actions."""
        # Extract actions directly from tool_data (tool already validated by responder)
        actions = tool_data.get("actions", ["stay"])
        reasoning = tool_data.get("reasoning", "No reasoning provided")
        
        # Initialize result that will accumulate all actions
        result = ToolExecutionResult(
            updates={},
            navigation=None,
            escalate=False,
            terminal=False,
            metadata={META_REASONING: reasoning}
        )
        
        # Process each action in sequence
        for action in actions:
            if action == "stay":
                # Increment clarification count if needed
                clarification_reason = tool_data.get("clarification_reason")
                if clarification_reason == CLARIFICATION_NEEDS_EXPLANATION:
                    context.clarification_count += 1
                result.metadata["clarification_reason"] = clarification_reason
                # Stay doesn't change navigation or updates
                
            elif action == "update":
                # Add updates to the result
                updates = tool_data.get("updates")
                if updates:
                    result.updates.update(updates)
                    # Also update context immediately
                    context.answers.update(updates)
                
            elif action == "navigate":
                # Set navigation target
                result.navigation = tool_data.get("target_node_id")
                result.metadata[META_NAV_TYPE] = "explicit"
                
            elif action == "handoff":
                # Mark for escalation
                result.escalate = True
                result.metadata["reason"] = tool_data.get("handoff_reason") or "requested"
                
            elif action == "complete":
                # Mark as terminal
                result.terminal = True
                
            elif action == "restart":
                # Reset context state
                context.answers.clear()
                context.path_confidence.clear()
                context.clarification_count = DEFAULT_CLARIFICATION_COUNT
                context.path_corrections = DEFAULT_PATH_CORRECTIONS
                context.active_path = None
                context.is_complete = False
                # Navigate to entry node
                result.navigation = context.flow_id
                result.metadata[META_RESTART] = True
                
        
        return result

    def _create_empty_result(self) -> ToolExecutionResult:
        """Create an empty result for fallback cases."""
        return ToolExecutionResult(
            updates={},
            navigation=None,
            escalate=False,
            terminal=False,
            metadata={}
        )
    
    def _handle_modify_flow_live(
        self,
        tool_data: dict[str, Any],
        context: FlowContext,
    ) -> ToolExecutionResult:
        """Handle ModifyFlowLive tool for admin users.
        
        Args:
            tool_data: Tool parameters including instruction
            context: Current flow context
            
        Returns:
            Execution result with modification metadata
        """
        instruction = tool_data.get("instruction", "")
        target_node = tool_data.get("target_node")
        modification_type = tool_data.get("modification_type", "general")
        
        logger.info(f"Admin flow modification requested: {instruction}")
        logger.info(f"Target node: {target_node}, Type: {modification_type}")
        
        # Store the modification instruction in metadata
        # The actual modification will be handled by the flow processor
        return ToolExecutionResult(
            updates={},
            navigation=None,
            escalate=False,
            terminal=False,
            metadata={
                "flow_modification_requested": True,
                "modification_instruction": instruction,
                "target_node": target_node,
                "modification_type": modification_type,
                "admin_action": True,
            },
        )
