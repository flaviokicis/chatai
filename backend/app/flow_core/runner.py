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
from .services.responder import EnhancedFlowResponder
from .services.tool_executor import ToolExecutionResult, ToolExecutionService
from .state import FlowContext

logger = logging.getLogger(__name__)


# Alias for backward compatibility during transition
TurnResult = ToolExecutionResult


class FlowTurnRunner:
    """Flow turn runner with external action feedback loops.

    This runner ensures that:
    1. External actions are actually executed
    2. Results are fed back to the LLM
    3. The LLM can only make truthful claims about action outcomes
    4. Users receive accurate information about what happened
    """

    def __init__(
        self,
        llm_client: LLMClient,
        compiled_flow: Any,
        action_registry: ActionRegistry | None = None,
    ):
        """Initialize the flow runner.

        Args:
            llm_client: LLM client for generating responses
            compiled_flow: Compiled flow definition
            action_registry: Optional pre-created action registry (for reuse)
        """
        self._llm_client = llm_client
        self._compiled_flow = compiled_flow

        # Initialize components - reuse action registry if provided
        self._action_registry = action_registry or ActionRegistry(llm_client)
        self._responder = EnhancedFlowResponder(llm_client)
        self._tool_executor = ToolExecutionService(self._action_registry)
        self._feedback_loop = FeedbackLoop(self._responder)

        logger.info("FlowTurnRunner initialized")

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
    ) -> ToolExecutionResult:
        """Process a single turn in the flow with external action support."""
        logger.info(f"Processing turn for user message: '{user_message}'")
        try:
            # Build flow graph from compiled flow
            flow_graph = (
                {
                    "id": self._compiled_flow.id,
                    "entry": self._compiled_flow.entry,
                    "nodes": [node.model_dump() for node in self._compiled_flow.nodes.values()],
                    "edges": [
                        {
                            "from": from_id,
                            "to": edge.target,
                            "condition": edge.condition_description or edge.label or "",
                            "priority": edge.priority,
                        }
                        for from_id, edges in self._compiled_flow.edges_from.items()
                        for edge in edges
                    ],
                }
                if self._compiled_flow
                else None
            )

            # Get available edges from current node
            available_edges = []
            if ctx.current_node_id and self._compiled_flow:
                edges_from_current = self._compiled_flow.edges_from.get(ctx.current_node_id, [])
                available_edges = [
                    {
                        "target_node_id": edge.target,
                        "condition": edge.condition_description or edge.label or "",
                        "priority": edge.priority,
                    }
                    for edge in edges_from_current
                ]

            # Get the current node to find pending field
            current_node = None
            pending_field = ctx.pending_field
            if ctx.current_node_id and self._compiled_flow:
                current_node = self._compiled_flow.nodes.get(ctx.current_node_id)
                if current_node and hasattr(current_node, "data_key"):
                    pending_field = current_node.data_key

            # Step 1: Get initial LLM response with full context
            responder_output = await self._responder.respond(
                prompt=current_node.text if current_node and hasattr(current_node, "text") else "",
                pending_field=pending_field,
                context=ctx,
                user_message=user_message,
                project_context=project_context,
                is_admin=is_admin,
                flow_graph=flow_graph,
                available_edges=available_edges,
            )

            # Store messages from responder in the tool result metadata
            if responder_output.messages:
                responder_output.tool_result.metadata["messages"] = responder_output.messages

            llm_response = {
                "tool_calls": [
                    {
                        "name": responder_output.tool_name,
                        "arguments": responder_output.tool_result.metadata,
                    }
                ]
                if responder_output.tool_name and responder_output.tool_result
                else []
            }

            # Step 2: Process tool calls
            tool_result = await self._process_tool_calls(llm_response, ctx)

            # Ensure messages from responder are preserved in tool_result
            if responder_output.messages and not tool_result.metadata.get("messages"):
                tool_result.metadata["messages"] = responder_output.messages

            # Step 3: Feedback if needed
            final_response = llm_response
            if tool_result.requires_llm_feedback:
                final_response = await self._handle_external_action_feedback(
                    llm_response, tool_result, ctx
                )

            # Step 4: Return the primary, typed result, enriched with messages
            if final_response.get("tool_calls"):
                args = final_response["tool_calls"][0].get("arguments", {})
                msgs = args.get("messages")
                if msgs:
                    # IMPORTANT: Replace messages with feedback messages, don't just setdefault
                    tool_result.metadata["messages"] = msgs

            return tool_result

        except Exception as e:
            logger.error("Error in turn processing", exc_info=True)
            return ToolExecutionResult(
                metadata={"error": str(e)},
            )

    async def _process_tool_calls(
        self,
        llm_response: dict[str, Any],
        ctx: FlowContext,
    ) -> ToolExecutionResult:
        """Process tool calls from the LLM response and return single result."""
        if "tool_calls" not in llm_response or not llm_response["tool_calls"]:
            return ToolExecutionResult()

        tool_call = llm_response["tool_calls"][0]
        tool_name = tool_call.get("name", "UnknownTool")
        tool_args = tool_call.get("arguments", {})
        logger.info(f"Executing tool: {tool_name}")
        return await self._tool_executor.execute_tool(tool_name, tool_args, ctx)

    async def _handle_external_action_feedback(
        self,
        original_response: dict[str, Any],
        tool_result: ToolExecutionResult,
        ctx: FlowContext,
    ) -> dict[str, Any]:
        """Handle feedback for external actions."""
        if not tool_result.external_action_result:
            return original_response

        original_messages = None
        original_instruction = None
        if original_response.get("tool_calls"):
            tool_call = original_response["tool_calls"][0]
            if "arguments" in tool_call:
                original_messages = tool_call["arguments"].get("messages")
                original_instruction = tool_call["arguments"].get("flow_modification_instruction")

        feedback_result = await self._feedback_loop.process_action_result(
            action_name="modify_flow",
            action_result=tool_result.external_action_result,
            context=ctx,
            original_messages=original_messages,
            original_instruction=original_instruction,
        )

        return {
            "tool_calls": [
                {
                    "name": "PerformAction",
                    "arguments": {
                        "messages": feedback_result["messages"],
                        "actions": ["stay"],
                        "confidence": 0.95,
                        "reasoning": "Responding based on actual modify_flow result",
                    },
                }
            ]
        }
