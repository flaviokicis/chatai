"""Clean flow runner with external action feedback support.

This runner provides a clean architecture that ensures the LLM is always
aware of the actual results of external actions, preventing false promises.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

from .actions import ActionRegistry
from .feedback import FeedbackLoop
from .result_types import FlowProcessingResult, ToolExecutionResult
from .services.responder import EnhancedFlowResponder
from .services.tool_executor import ToolExecutionService
from .state import FlowContext

logger = logging.getLogger(__name__)


# Alias for backward compatibility during transition
TurnResult = FlowProcessingResult


class FlowTurnRunner:
    """Clean flow runner with external action feedback loops.
    
    This runner ensures that:
    1. External actions are actually executed
    2. Results are fed back to the LLM
    3. The LLM can only make truthful claims about action outcomes
    4. Users receive accurate information about what happened
    """

    def __init__(self, llm_client: LLMClient, compiled_flow: Any):
        """Initialize the flow runner.
        
        Args:
            llm_client: LLM client for generating responses
            compiled_flow: Compiled flow definition
        """
        self._llm_client = llm_client
        self._compiled_flow = compiled_flow

        # Initialize clean architecture components
        self._action_registry = ActionRegistry(llm_client)
        self._responder = EnhancedFlowResponder(llm_client)
        self._tool_executor = ToolExecutionService(self._action_registry)
        self._feedback_loop = FeedbackLoop(self._responder)

        logger.info("FlowTurnRunner initialized with clean architecture")

    def initialize_context(self, existing_context: FlowContext | None = None) -> FlowContext:
        """Initialize or update flow context.
        
        Args:
            existing_context: Existing context to update, if any
            
        Returns:
            Initialized flow context
        """
        if existing_context:
            return existing_context

        # Create new context
        return FlowContext(
            user_id="",
            session_id="",
            tenant_id="",
            channel_id="",
            flow_id="",
            current_node_id="",
            answers={},
            history=[],
        )

    async def process_turn(
        self,
        ctx: FlowContext,
        user_message: str,
        project_context: ProjectContext | None = None,
        is_admin: bool = False,
    ) -> FlowProcessingResult:
        """Process a single turn in the flow with external action support."""
        logger.info(f"Processing turn for user message: '{user_message}'")
        try:
            # Step 1: Get initial LLM response
            responder_output = await self._responder.respond(
                prompt="",
                pending_field=None,
                context=ctx,
                user_message=user_message,
                project_context=project_context,
                is_admin=is_admin,
            )

            # This is a temporary adaptation of the old responder_output format
            llm_response = {
                "tool_calls": [
                    { "name": responder_output.tool_name, "arguments": responder_output.tool_result.metadata }
                ] if responder_output.tool_name and responder_output.tool_result else []
            }

            # Step 2: Process tool calls
            tool_results = await self._process_tool_calls(llm_response, ctx)

            # Step 3: Handle external action feedback if needed
            # This part of the logic remains complex and may need further review.
            final_response = llm_response
            primary_tool_result = tool_results[0] if tool_results else None
            if primary_tool_result and primary_tool_result.requires_llm_feedback:
                final_response = await self._handle_external_action_feedback(
                    llm_response, primary_tool_result, ctx
                )

            # Step 4: Build turn result
            return self._build_turn_result(final_response, tool_results, ctx)

        except Exception as e:
            logger.error("Error in turn processing", exc_info=True)
            return FlowProcessingResult(
                success=False,
                assistant_message="Desculpe, ocorreu um erro interno. Tente novamente.",
                errors=[str(e)],
                confidence=0.0
            )

    async def _process_tool_calls(
        self,
        llm_response: dict[str, Any],
        ctx: FlowContext,
    ) -> list[ToolExecutionResult]:
        """Process tool calls from the LLM response."""

        tool_results: list[ToolExecutionResult] = []

        if "tool_calls" not in llm_response or not llm_response["tool_calls"]:
            return tool_results

        for tool_call in llm_response["tool_calls"]:
            tool_name = tool_call.get("name", "UnknownTool")
            tool_args = tool_call.get("arguments", {})

            logger.info(f"Executing tool: {tool_name}")

            # The actual execution is now done inside the tool executor service
            # For now, we are adapting the old structure.
            # This part needs to be fully refactored to use the new service correctly.

            # Placeholder for actual execution logic
            tool_result = await self._tool_executor.execute_tool(tool_name, tool_args, ctx)

            # We must convert the result from the old service to the new typed object.
            # This is a temporary bridge during refactoring.

            new_tool_result = ToolExecutionResult(
                tool_name=tool_name,
                success=tool_result.external_action_result.success if tool_result.external_action_result else True,
                arguments=tool_args,
                result_data={
                    "updates": tool_result.updates,
                    "navigation": tool_result.navigation,
                    "escalate": tool_result.escalate,
                    "terminal": tool_result.terminal,
                    "metadata": tool_result.metadata,
                },
                external_action_executed=tool_result.external_action_executed,
                external_action_result=tool_result.external_action_result
            )
            tool_results.append(new_tool_result)

        return tool_results

    async def _handle_external_action_feedback(
        self,
        original_response: dict[str, Any],
        tool_result: Any,
        ctx: FlowContext,
    ) -> dict[str, Any]:
        """Handle feedback for external actions.
        
        Args:
            original_response: Original LLM response
            tool_result: Tool execution result
            ctx: Flow context
            
        Returns:
            Updated response based on actual action results
        """
        if not tool_result.external_action_result:
            return original_response

        # Extract original messages and instruction
        original_messages = None
        original_instruction = None

        if original_response.get("tool_calls"):
            tool_call = original_response["tool_calls"][0]
            if "arguments" in tool_call:
                original_messages = tool_call["arguments"].get("messages")
                original_instruction = tool_call["arguments"].get("flow_modification_instruction")

        # Process through feedback loop
        action_name = "modify_flow"  # For now, we only have flow modification
        feedback_result = await self._feedback_loop.process_action_result(
            action_name=action_name,
            action_result=tool_result.external_action_result,
            context=ctx,
            original_messages=original_messages,
            original_instruction=original_instruction,
        )

        # Build updated response
        return {
            "tool_calls": [{
                "name": "PerformAction",
                "arguments": {
                    "messages": feedback_result["messages"],
                    "actions": ["stay"],  # Always stay after external action
                    "confidence": 0.95,
                    "reasoning": f"Responding based on actual {action_name} result"
                }
            }]
        }

    def _build_turn_result(
        self,
        final_response: dict[str, Any],
        tool_execution_results: list[ToolExecutionResult],
        ctx: FlowContext
    ) -> FlowProcessingResult:
        """Build the final turn result using typed objects."""

        messages = []
        reasoning = None

        if final_response.get("tool_calls"):
            tool_call = final_response["tool_calls"][0]
            tool_args = tool_call.get("arguments", {})
            messages = tool_args.get("messages", [])
            reasoning = tool_args.get("reasoning")

        assistant_message = messages[0].get("text", "") if messages else None

        primary_tool_result = tool_execution_results[0] if tool_execution_results else None

        # Aggregate data from all tool executions
        answers_diff = {}
        for res in tool_execution_results:
            if hasattr(res, "result_data") and res.result_data:
                updates = res.result_data.get("updates", {})
                if isinstance(updates, dict):
                    answers_diff.update(updates)

        return FlowProcessingResult(
            success=True,  # Assuming success if we reach this point
            assistant_message=assistant_message,
            messages=messages,
            tool_executions=tool_execution_results,
            answers_diff=answers_diff,
            terminal=primary_tool_result.result_data.get("terminal", False) if primary_tool_result and primary_tool_result.result_data else False,
            escalate=primary_tool_result.result_data.get("escalate", False) if primary_tool_result and primary_tool_result.result_data else False,
            reasoning=reasoning,
            confidence=primary_tool_result.result_data.get("confidence", 1.0) if primary_tool_result and primary_tool_result.result_data else 1.0,
        )
