"""Clean flow runner with external action feedback support.

This runner provides a clean architecture that ensures the LLM is always
aware of the actual results of external actions, preventing false promises.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

from .actions import ActionRegistry
from .feedback import FeedbackLoop
from .result_types import FlowExecutionContext, FlowProcessingResult, ToolExecutionResult
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
    ) -> TurnResult:
        """Process a single turn in the flow with external action support.
        
        Args:
            ctx: Current flow context
            user_message: User's message
            project_context: Project context for the flow
            is_admin: Whether the user has admin privileges
            
        Returns:
            Turn result with proper external action feedback
        """
        logger.info("=" * 80)
        logger.info("🎯 FLOW TURN RUNNER: Processing turn")
        logger.info("=" * 80)
        logger.info(f"User message: {user_message[:100]}..." if len(user_message) > 100 else f"User message: {user_message}")
        logger.info(f"Current node: {ctx.current_node_id}")
        logger.info(f"Is admin: {is_admin}")
        logger.info("=" * 80)

        try:
            # Add user message to history
            from .state import ConversationTurn
            from datetime import datetime
            ctx.history.append(ConversationTurn(
                timestamp=datetime.now(),
                role="user",
                content=user_message,
                node_id=None,
                metadata={}
            ))

            # Step 1: Get initial LLM response using existing responder interface
            logger.info("🤖 Step 1: Getting initial LLM response...")
            responder_output = await self._responder.respond(
                prompt="",  # Will be built internally
                pending_field=None,
                context=ctx,
                user_message=user_message,
                project_context=project_context,
                is_admin=is_admin,
            )
            
            # Convert responder output to our expected format
            llm_response = {
                "tool_calls": [
                    {
                        "name": responder_output.tool_name,
                        "arguments": responder_output.tool_result.metadata if responder_output.tool_result else {}
                    }
                ] if responder_output.tool_name else []
            }

            # Step 2: Use tool result from responder when available to avoid double execution
            logger.info("🔧 Step 2: Processing tool calls / using existing tool result...")
            if hasattr(responder_output, "tool_result") and responder_output.tool_result:
                tool_result = responder_output.tool_result
            else:
                tool_result = await self._process_tool_calls(llm_response, ctx)

            # Step 3: Handle external action feedback if needed
            final_response = llm_response
            if tool_result.requires_llm_feedback:
                logger.info("🔄 Step 3: Processing external action feedback...")
                final_response = await self._handle_external_action_feedback(
                    llm_response, tool_result, ctx
                )

            # Step 4: Build turn result
            turn_result = self._build_turn_result(final_response, tool_result, ctx)
            
            logger.info("=" * 80)
            logger.info("✅ TURN PROCESSING COMPLETED")
            logger.info("=" * 80)
            logger.info(f"Messages: {len(turn_result.messages) if turn_result.messages else 0}")
            logger.info(f"External action executed: {turn_result.external_action_executed}")
            logger.info(f"External action successful: {turn_result.external_action_successful}")
            logger.info("=" * 80)

            return turn_result

        except Exception as e:
            logger.error("❌ Error in turn processing", exc_info=True)
            return TurnResult(
                assistant_message="❌ Desculpe, ocorreu um erro interno. Tente novamente.",
                metadata={"error": str(e)},
                confidence=0.0
            )

    async def _process_tool_calls(self, llm_response: dict[str, Any], ctx: FlowContext) -> Any:
        """Process tool calls from the LLM response.
        
        Args:
            llm_response: Response from the LLM
            ctx: Flow context
            
        Returns:
            Tool execution result
        """
        if "tool_calls" not in llm_response or not llm_response["tool_calls"]:
            # No tools to execute
            from .services.tool_executor import ToolExecutionResult
            return ToolExecutionResult()

        tool_call = llm_response["tool_calls"][0]  # We expect only one tool call
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("arguments", {})

        logger.info(f"Executing tool: {tool_name}")
        return await self._tool_executor.execute_tool(tool_name, tool_args, ctx)

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
        
        if "tool_calls" in original_response and original_response["tool_calls"]:
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
        tool_result: Any, 
        ctx: FlowContext
    ) -> TurnResult:
        """Build the final turn result.
        
        Args:
            final_response: Final LLM response (possibly with feedback)
            tool_result: Tool execution result
            ctx: Flow context
            
        Returns:
            Complete turn result
        """
        # Extract messages from response
        messages = []
        tool_name = None
        tool_args = None
        reasoning = None

        if "tool_calls" in final_response and final_response["tool_calls"]:
            tool_call = final_response["tool_calls"][0]
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("arguments", {})
            messages = tool_args.get("messages", [])
            reasoning = tool_args.get("reasoning")

        # Determine assistant message (first message text)
        assistant_message = None
        if messages:
            assistant_message = messages[0].get("text", "")

        return TurnResult(
            assistant_message=assistant_message,
            messages=messages,
            tool_name=tool_name,
            tool_args=tool_args,
            answers_diff=tool_result.updates if hasattr(tool_result, 'updates') else {},
            metadata=tool_result.metadata if hasattr(tool_result, 'metadata') else {},
            terminal=tool_result.terminal if hasattr(tool_result, 'terminal') else False,
            escalate=tool_result.escalate if hasattr(tool_result, 'escalate') else False,
            external_action_executed=tool_result.external_action_executed if hasattr(tool_result, 'external_action_executed') else False,
            external_action_successful=(
                tool_result.external_action_result.is_success 
                if hasattr(tool_result, 'external_action_result') and tool_result.external_action_result 
                else None
            ),
            reasoning=reasoning,
            confidence=tool_args.get("confidence", 1.0) if tool_args else 1.0,
        )
