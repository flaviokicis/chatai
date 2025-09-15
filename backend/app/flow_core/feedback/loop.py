"""Feedback loop implementation for external action results.

This module implements the feedback loop that ensures the LLM receives
and processes the actual results of external actions.
"""

from __future__ import annotations

import logging
from typing import Any

from ..actions import ActionResult
from ..services.responder import EnhancedFlowResponder
from ..state import FlowContext
from .prompts import FeedbackPromptBuilder

logger = logging.getLogger(__name__)


class FeedbackLoop:
    """Manages the feedback loop between external actions and the LLM.

    This class ensures that when external actions are executed, their results
    are fed back to the LLM for proper acknowledgment and truthful responses.
    """

    def __init__(self, responder: EnhancedFlowResponder):
        """Initialize the feedback loop.

        Args:
            responder: The flow responder for LLM communication
        """
        self._responder = responder
        self._prompt_builder = FeedbackPromptBuilder()

    async def process_action_result(
        self,
        action_name: str,
        action_result: ActionResult,
        context: FlowContext,
        original_messages: list[dict[str, Any]] | None = None,
        original_instruction: str | None = None,
        flow_graph: dict[str, Any] | None = None,
        available_edges: list[dict[str, Any]] | None = None,
        current_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Process an external action result through the LLM feedback loop.

        Args:
            action_name: Name of the action that was executed
            action_result: Result of the action execution
            context: Current flow context
            original_messages: Original messages the LLM intended to send
            original_instruction: Original instruction from the LLM

        Returns:
            Updated response from the LLM based on actual action result
        """
        logger.info("=" * 80)
        logger.info(f"🔄 FEEDBACK LOOP: Processing {action_name} result")
        logger.info("=" * 80)
        logger.info(f"Action succeeded: {action_result.is_success}")
        logger.info(f"Result message: {action_result.message}")
        if action_result.error:
            logger.info(f"Error details: {action_result.error}")
        logger.info("=" * 80)

        # Build feedback prompt
        result_prompt = self._prompt_builder.build_action_result_prompt(
            action_name, action_result, original_instruction
        )

        instruction_prompt = self._prompt_builder.build_action_feedback_instruction(
            action_name, action_result
        )

        # Create feedback context
        feedback_context = self._build_feedback_context(
            context, result_prompt, instruction_prompt, original_messages
        )

        try:
            # Get LLM response based on actual action result
            logger.info("🤖 Requesting LLM feedback response...")
            # Use responder.respond (async) to generate a truthful response based on action result
            responder_output = await self._responder.respond(
                prompt=current_prompt or f"Action '{action_name}' completed: {action_result.message}",
                pending_field=context.pending_field,
                context=feedback_context,
                user_message=result_prompt,  # The action result becomes the "message" to respond to
                project_context=None,
                is_admin=True,
                flow_graph=flow_graph,
                available_edges=available_edges,
            )

            # Convert responder output into a simulated llm_response structure
            llm_response = {
                "tool_calls": [
                    {
                        "name": responder_output.tool_name,
                        "arguments": {
                            "messages": responder_output.messages,
                            "confidence": responder_output.confidence,
                            "reasoning": responder_output.reasoning or "",
                        },
                    }
                ]
                if responder_output.tool_name
                else []
            }

            logger.info("✅ LLM feedback response generated")
            return self._extract_truthful_response(llm_response, action_result)

        except Exception as e:
            logger.error(f"❌ Error in feedback loop: {e}", exc_info=True)
            # Fallback to a truthful error response
            return self._create_fallback_response(action_name, action_result)

    def _build_feedback_context(
        self,
        original_context: FlowContext,
        result_prompt: str,
        instruction_prompt: str,
        original_messages: list[dict[str, Any]] | None,
    ) -> FlowContext:
        """Build a context for the feedback loop.

        Args:
            original_context: Original flow context
            result_prompt: Prompt with action result details
            instruction_prompt: Instruction for handling the result
            original_messages: Original messages from the LLM

        Returns:
            Updated context for feedback
        """
        # Create a copy of the context for feedback
        feedback_context = FlowContext(
            user_id=original_context.user_id,
            session_id=original_context.session_id,
            tenant_id=original_context.tenant_id,
            channel_id=original_context.channel_id,
            flow_id=original_context.flow_id,
            current_node_id=original_context.current_node_id,
            answers=original_context.answers.copy(),
            history=original_context.history.copy(),
        )

        # Add feedback information to history using ConversationTurn
        from datetime import datetime

        from ..state import ConversationTurn

        feedback_context.history.append(
            ConversationTurn(
                timestamp=datetime.now(),
                role="system",
                content=result_prompt,
                node_id=None,
                metadata={},
            )
        )

        feedback_context.history.append(
            ConversationTurn(
                timestamp=datetime.now(),
                role="system",
                content=instruction_prompt,
                node_id=None,
                metadata={},
            )
        )

        if original_messages:
            # Use system role to annotate draft content in a typed-safe way
            feedback_context.history.append(
                ConversationTurn(
                    timestamp=datetime.now(),
                    role="system",
                    content=f"Original intended messages: {original_messages}",
                    node_id=None,
                    metadata={},
                )
            )

        return feedback_context

    def _extract_truthful_response(
        self, llm_response: dict[str, Any], action_result: ActionResult
    ) -> dict[str, Any]:
        """Extract and validate the truthful response from the LLM.

        Args:
            llm_response: Response from the LLM
            action_result: Actual action result

        Returns:
            Validated response
        """
        # Extract messages from the LLM response
        messages = []

        if llm_response.get("tool_calls"):
            tool_call = llm_response["tool_calls"][0]
            if "arguments" in tool_call and "messages" in tool_call["arguments"]:
                messages = tool_call["arguments"]["messages"]

        # Validate that the messages align with the actual result
        if not self._validate_response_truthfulness(messages, action_result):
            logger.warning("⚠️ LLM response doesn't align with action result, using fallback")
            return self._create_fallback_response("action", action_result)

        return {"messages": messages, "action_result": action_result, "truthful": True}

    def _validate_response_truthfulness(
        self, messages: list[dict[str, Any]], action_result: ActionResult
    ) -> bool:
        """Validate that the LLM response is truthful about the action result.

        Args:
            messages: Messages from the LLM
            action_result: Actual action result

        Returns:
            True if the response is truthful, False otherwise
        """
        if not messages:
            return False

        # Check if the response acknowledges the actual result
        response_text = " ".join(msg.get("text", "") for msg in messages).lower()

        if action_result.is_success:
            # For success, response should be positive
            success_indicators = ["sucesso", "aplicad", "modific", "✅", "pronto", "feito"]
            return any(indicator in response_text for indicator in success_indicators)
        # For failure, response should acknowledge the error
        error_indicators = ["erro", "falha", "não foi", "❌", "problema", "falhou"]
        return any(indicator in response_text for indicator in error_indicators)

    def _create_fallback_response(
        self, action_name: str, action_result: ActionResult
    ) -> dict[str, Any]:
        """Create a fallback response when the LLM feedback fails.

        Args:
            action_name: Name of the action
            action_result: Action result

        Returns:
            Fallback response
        """
        if action_result.is_success:
            messages = [{"text": action_result.message, "delay_ms": 0}]
        else:
            messages = [{"text": f"{action_result.message}", "delay_ms": 0}]

        return {
            "messages": messages,
            "action_result": action_result,
            "truthful": True,
            "fallback": True,
        }
