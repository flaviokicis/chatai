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
    DEFAULT_TURN_COUNT,
    META_NAV_TYPE,
    META_NEEDS_VALIDATION,
    META_REASONING,
    META_RESTART,
    META_VALIDATED,
    TOOL_CONFIRM_COMPLETION,
    TOOL_NAVIGATE_TO_NODE,
    TOOL_REQUEST_HANDOFF,
    TOOL_RESTART_CONVERSATION,
    TOOL_STAY_ON_NODE,
    TOOL_UPDATE_ANSWERS,
)
from ..types import (
    AnswersDict,
    ConfirmCompletionCall,
    MetadataDict,
    NavigateToNodeCall,
    RequestHumanHandoffCall,
    RestartConversationCall,
    StayOnThisNodeCall,
    ToolCallUnion,
    ToolExecutionError,
    UpdateAnswersCall,
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
            if tool_name == TOOL_STAY_ON_NODE:
                return self._handle_stay_on_node_typed(
                    StayOnThisNodeCall(**{"tool_name": tool_name, **tool_data}),
                    context,
                    pending_field,
                )
            if tool_name == TOOL_NAVIGATE_TO_NODE:
                return self._handle_navigate_typed(
                    NavigateToNodeCall(**{"tool_name": tool_name, **tool_data}),
                    context,
                    pending_field,
                )
            if tool_name == TOOL_UPDATE_ANSWERS:
                return self._handle_update_answers_typed(
                    UpdateAnswersCall(**{"tool_name": tool_name, **tool_data}),
                    context,
                    pending_field,
                )
            if tool_name == TOOL_REQUEST_HANDOFF:
                return self._handle_human_handoff_typed(
                    RequestHumanHandoffCall(**{"tool_name": tool_name, **tool_data}),
                    context,
                    pending_field,
                )
            if tool_name == TOOL_CONFIRM_COMPLETION:
                return self._handle_completion_typed(
                    ConfirmCompletionCall(**{"tool_name": tool_name, **tool_data}),
                    context,
                    pending_field,
                )
            if tool_name == TOOL_RESTART_CONVERSATION:
                return self._handle_restart_typed(
                    RestartConversationCall(**{"tool_name": tool_name, **tool_data}),
                    context,
                    pending_field,
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

    def execute_tool_typed(
        self,
        tool: ToolCallUnion,
        context: FlowContext,
        pending_field: str | None = None,
    ) -> ToolExecutionResult:
        """Execute a strongly-typed tool.
        
        Args:
            tool: The typed tool call
            context: Current flow context
            pending_field: Currently pending field (if any)
            
        Returns:
            Execution result with updates and navigation info
        """
        if isinstance(tool, StayOnThisNodeCall):
            return self._handle_stay_on_node_typed(tool, context, pending_field)
        if isinstance(tool, NavigateToNodeCall):
            return self._handle_navigate_typed(tool, context, pending_field)
        if isinstance(tool, UpdateAnswersCall):
            return self._handle_update_answers_typed(tool, context, pending_field)
        if isinstance(tool, RequestHumanHandoffCall):
            return self._handle_human_handoff_typed(tool, context, pending_field)
        if isinstance(tool, ConfirmCompletionCall):
            return self._handle_completion_typed(tool, context, pending_field)
        if isinstance(tool, RestartConversationCall):
            return self._handle_restart_typed(tool, context, pending_field)
        logger.warning(f"Unexpected tool type: {type(tool)}")
        return self._create_empty_result()

    def _handle_stay_on_node_typed(
        self,
        tool: StayOnThisNodeCall,
        context: FlowContext,
        pending_field: str | None,
    ) -> ToolExecutionResult:
        """Handle StayOnThisNode tool with strong typing."""
        # Increment clarification count if needed
        if tool.clarification_reason == CLARIFICATION_NEEDS_EXPLANATION:
            context.clarification_count += 1

        return ToolExecutionResult(
            updates={},
            navigation=None,  # Stay on current node
            escalate=False,
            terminal=False,
            metadata={
                "acknowledgment": tool.acknowledgment,
                "clarification_reason": tool.clarification_reason,
                META_REASONING: tool.reasoning,
            }
        )

    def _handle_navigate_typed(
        self,
        tool: NavigateToNodeCall,
        context: FlowContext,
        pending_field: str | None,
    ) -> ToolExecutionResult:
        """Handle NavigateToNode tool with strong typing."""
        return ToolExecutionResult(
            updates={},
            navigation=tool.target_node_id,
            escalate=False,
            terminal=False,
            metadata={
                META_NAV_TYPE: tool.navigation_type,
                META_REASONING: tool.reasoning,
            }
        )

    def _handle_update_answers_typed(
        self,
        tool: UpdateAnswersCall,
        context: FlowContext,
        pending_field: str | None,
    ) -> ToolExecutionResult:
        """Handle UpdateAnswers tool with strong typing."""
        # Updates are guaranteed to exist by Pydantic validation
        updates = tool.updates

        # Apply validation if needed
        if pending_field and pending_field in updates and not tool.validated:
            # Mark for validation in the context
            node_state = context.get_node_state(context.current_node_id or "")
            node_state.metadata[META_NEEDS_VALIDATION] = True

        return ToolExecutionResult(
            updates=updates,
            navigation=None,
            escalate=False,
            terminal=False,
            metadata={
                META_VALIDATED: tool.validated,
                META_REASONING: tool.reasoning,
            }
        )

    def _handle_human_handoff_typed(
        self,
        tool: RequestHumanHandoffCall,
        context: FlowContext,
        pending_field: str | None,
    ) -> ToolExecutionResult:
        """Handle RequestHumanHandoff tool with strong typing."""
        return ToolExecutionResult(
            updates={},
            navigation=None,
            escalate=True,
            terminal=False,
            metadata={
                "reason": tool.reason,
                "context_summary": tool.context_summary,
                "urgency": tool.urgency,
                META_REASONING: tool.reasoning,
            }
        )

    def _handle_completion_typed(
        self,
        tool: ConfirmCompletionCall,
        context: FlowContext,
        pending_field: str | None,
    ) -> ToolExecutionResult:
        """Handle ConfirmCompletion tool with strong typing."""
        context.is_complete = True

        return ToolExecutionResult(
            updates={},
            navigation=None,
            escalate=False,
            terminal=True,
            metadata={
                "summary": tool.summary,
                "next_steps": tool.next_steps,
                "completion_type": tool.completion_type,
                META_REASONING: tool.reasoning,
            }
        )

    def _handle_restart_typed(
        self,
        tool: RestartConversationCall,
        context: FlowContext,
        pending_field: str | None,
    ) -> ToolExecutionResult:
        """Handle RestartConversation tool with strong typing."""
        # Clear context
        context.answers.clear()
        context.node_states.clear()
        context.clarification_count = DEFAULT_CLARIFICATION_COUNT
        context.path_corrections = DEFAULT_PATH_CORRECTIONS
        context.active_path = None
        context.is_complete = False

        if tool.clear_history:
            context.history.clear()
            context.turn_count = DEFAULT_TURN_COUNT

        # Return to entry node
        return ToolExecutionResult(
            updates={},
            navigation=context.flow_id,  # Will be resolved to entry node
            escalate=False,
            terminal=False,
            metadata={
                META_REASONING: tool.reasoning,
                META_RESTART: True,
            }
        )

    def _create_empty_result(self) -> ToolExecutionResult:
        """Create an empty result for fallback cases."""
        return ToolExecutionResult(
            updates={},
            navigation=None,
            escalate=False,
            terminal=False,
            metadata={}
        )
