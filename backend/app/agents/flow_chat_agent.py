"""Flow chat agent - Single tool call architecture.

This module implements the flow chat agent that uses a single
LLM call with one tool that outputs multiple actions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, NamedTuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.llm import LLMClient
from app.services.flow_modification_service import (
    BatchFlowActionsRequest,
    FlowModificationService,
)
from app.settings import is_development_mode

logger = logging.getLogger(__name__)

# Maximum retries for LLM calls
MAX_LLM_RETRIES = 2

# Timeout for LLM calls (seconds)
LLM_TIMEOUT = 60


class FlowChatResponse(NamedTuple):
    """Response from the flow chat agent."""

    messages: list[str]
    flow_was_modified: bool
    modification_summary: str | None = None


class FlowChatAgent:
    """LLM-driven agent for flow modification using single tool architecture.

    This agent:
    - Makes exactly ONE LLM call per user request
    - Uses a single tool that accepts multiple actions
    - Provides comprehensive error handling and retries
    - Logs everything important for debugging in production
    """

    def __init__(self, llm: LLMClient):
        """Initialize the agent with an LLM client."""
        self.llm = llm

    async def process(
        self,
        flow: dict[str, Any],
        history: list[dict[str, str]],
        flow_id: UUID | None = None,
        session: Session | None = None,
        simplified_view_enabled: bool = False,
        active_path: str | None = None,
    ) -> FlowChatResponse:
        """Process a user message and modify the flow as needed.

        Args:
            flow: Current flow definition
            history: Conversation history
            flow_id: Optional flow ID for persistence
            session: Optional database session
            simplified_view_enabled: Whether simplified view is enabled
            active_path: Currently active path in simplified view

        Returns:
            FlowChatResponse with messages and modification status
        """
        logger.info("=" * 80)
        logger.info("🤖 FLOW CHAT AGENT V2: Starting processing")
        logger.info("=" * 80)
        logger.info(f"Flow ID: {flow_id}")
        logger.info(f"History length: {len(history)}")
        logger.info(f"Simplified view: {simplified_view_enabled}")
        logger.info(f"Active path: {active_path}")
        if history:
            last_msg = history[-1]
            logger.info(
                f"Last message ({last_msg['role']}): {last_msg['content'][:200]}..."
                if len(last_msg["content"]) > 200
                else f"Last message ({last_msg['role']}): {last_msg['content']}"
            )
        logger.info("=" * 80)

        # Build the prompt
        prompt = self._build_prompt(flow, history, simplified_view_enabled, active_path)

        # Log prompt in development mode
        if is_development_mode():
            self._log_prompt_debug(prompt, "initial")

        # Try to get response from LLM with retries
        result = None
        last_error = None

        for attempt in range(MAX_LLM_RETRIES):
            try:
                logger.info(f"LLM call attempt {attempt + 1}/{MAX_LLM_RETRIES}")

                # Make the LLM call with timeout
                result = await self._call_llm_with_timeout(prompt)

                if result:
                    logger.info(f"LLM call successful on attempt {attempt + 1}")
                    break

            except TimeoutError:
                last_error = "LLM call timed out"
                logger.error(f"Attempt {attempt + 1} timed out after {LLM_TIMEOUT}s")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Attempt {attempt + 1} failed: {e}", exc_info=True)

            if attempt < MAX_LLM_RETRIES - 1:
                await asyncio.sleep(2**attempt)  # Exponential backoff

        if not result:
            error_msg = f"Failed after {MAX_LLM_RETRIES} attempts: {last_error}"
            logger.error(error_msg)
            return FlowChatResponse(
                messages=[
                    "Desculpe, estou com dificuldades técnicas no momento. Nossa equipe já foi notificada."
                ],
                flow_was_modified=False,
                modification_summary=None,
            )

        # Process the LLM response
        return await self._process_llm_response(result, flow, flow_id, session, history)

    async def _call_llm_with_timeout(self, prompt: str) -> dict[str, Any] | None:
        """Call LLM with timeout protection."""
        loop = asyncio.get_event_loop()

        # Define the tool schema for batch actions
        tool_schema = BatchFlowActionsRequest

        # Run LLM call in executor with timeout
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self.llm.extract, prompt, [tool_schema]),
                timeout=LLM_TIMEOUT,
            )
            return result
        except TimeoutError:
            raise
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            raise

    async def _process_llm_response(
        self,
        llm_result: dict[str, Any],
        flow: dict[str, Any],
        flow_id: UUID | None,
        session: Session | None,
        history: list[dict[str, str]],
    ) -> FlowChatResponse:
        """Process the LLM response and execute actions."""
        content = llm_result.get("content", "")
        tool_calls = llm_result.get("tool_calls", [])

        logger.info(f"LLM response: content_len={len(content)}, tool_calls={len(tool_calls)}")

        # If no tool calls, just return the content
        if not tool_calls:
            if content:
                return FlowChatResponse(
                    messages=[content], flow_was_modified=False, modification_summary=None
                )
            return FlowChatResponse(
                messages=["Como posso ajudar você com o fluxo?"],
                flow_was_modified=False,
                modification_summary=None,
            )

        # Execute the batch actions
        tool_call = tool_calls[0]  # We expect only one tool call
        actions = tool_call.get("arguments", {}).get("actions", [])

        if not actions:
            logger.warning("Tool call had no actions")
            return FlowChatResponse(
                messages=[content] if content else ["Nenhuma ação foi especificada."],
                flow_was_modified=False,
                modification_summary=None,
            )

        logger.info("=" * 80)
        logger.info(f"🔧 EXECUTING BATCH OF {len(actions)} ACTIONS")
        logger.info("=" * 80)

        # Log actions for debugging
        for i, action in enumerate(actions):
            action_type = action.get("action", "unknown")
            node_id = action.get("node_id", "")
            source = action.get("source", "")
            target = action.get("target", "")

            logger.info(
                f"Action {i + 1}/{len(actions)}: {action_type} "
                f"node={node_id} edge={source}->{target}"
            )

        logger.info("=" * 80)

        # Execute actions using the service
        logger.info("🚀 Calling FlowModificationService.execute_batch_actions")
        service = FlowModificationService(session)

        try:
            result = service.execute_batch_actions(
                flow=flow, actions=actions, flow_id=flow_id, persist=bool(flow_id and session)
            )
        except Exception as e:
            logger.error("❌ FLOW MODIFICATION SERVICE FAILED")
            logger.error(f"Error: {e}", exc_info=True)
            raise

        if result.success:
            logger.info("=" * 80)
            logger.info("✅ FLOW MODIFICATION SUCCESSFUL")
            logger.info("=" * 80)
            logger.info(f"Actions executed: {len(actions)}")
            logger.info(f"Flow modified: {result.modified_flow is not None}")

            # Build modification summary
            summary_parts = []
            for action_result in result.action_results:
                if action_result.success:
                    summary_parts.append(action_result.message)

            modification_summary = "; ".join(summary_parts) if summary_parts else None

            # Get a meaningful message for the user
            if content and len(content) < 500:
                message = content
            else:
                message = f"✅ Fluxo modificado com sucesso! ({len(actions)} alterações aplicadas)"

            return FlowChatResponse(
                messages=[message],
                flow_was_modified=True,
                modification_summary=modification_summary,
            )
        logger.error("=" * 80)
        logger.error("❌ FLOW MODIFICATION FAILED")
        logger.error("=" * 80)
        logger.error(f"Error: {result.error}")

        # Log individual action results for debugging
        for i, action_result in enumerate(result.action_results):
            if not action_result.success:
                logger.error(
                    f"Action {i + 1} failed: {action_result.action_type} - {action_result.error}"
                )
        logger.error("=" * 80)

        error_message = f"❌ Erro ao modificar o fluxo: {result.error}"

        return FlowChatResponse(
            messages=[error_message], flow_was_modified=False, modification_summary=None
        )

    def _build_prompt(
        self,
        flow: dict[str, Any],
        history: list[dict[str, str]],
        simplified_view_enabled: bool,
        active_path: str | None,
    ) -> str:
        """Build the prompt for the LLM."""
        lines = []

        # System instructions
        lines.extend(
            [
                "You are an expert flow editing assistant that modifies conversation flows.",
                "You help users create and modify flows using a JSON-based flow language.",
                "",
                "## HOW FLOWS WORK AT RUNTIME:",
                "",
                "During conversations, flows guide the bot through steps as a state machine:",
                "",
                "**Execution Flow:**",
                "1. Start at entry node (specified by 'entry' field)",
                "2. Process current node (ask question, make decision, or end)",
                "3. Navigate via edges to next node",
                "4. Repeat until Terminal node",
                "",
                "**Node Behavior:**",
                "- Question: Bot asks the prompt, waits for answer, stores in answers[key]",
                "- Decision: Bot evaluates outgoing edges to choose next path",
                "- Terminal: Conversation ends",
                "",
                "**Edge Navigation:**",
                "- Edges define transitions (source -> target)",
                "- Multiple edges = multiple possible paths",
                "- Evaluated by PRIORITY (0=highest, checked first)",
                "- First edge whose GUARD passes is taken",
                "",
                "**Guards (Conditions):**",
                '- {"fn": "always"} → Always take this edge',
                '- {"fn": "answers_has", "args": {"key": "email"}} → Only if email was collected',
                '- {"fn": "answers_equals", "args": {"key": "product", "value": "premium"}} → Only if product="premium"',
                "- No guard = same as always",
                "",
                "**Why Structure Matters:**",
                "✅ One question per node → Clear, natural conversation",
                "✅ Connected edges → No orphaned/unreachable nodes",
                "✅ Proper priorities → Predictable routing",
                "✅ Guards on Decision edges → Conditional branching",
                "",
                "❌ Multiple questions per prompt → Confusing, hard to navigate",
                "❌ Missing edges → Dead ends",
                "❌ Orphaned nodes → Unreachable code",
                "",
                "**Navigation Example:**",
                "```",
                "q.name (asks 'What's your name?')",
                "  -> edge (priority 0, no guard) ->",
                "q.email (asks 'What's your email?')",
                "  -> edge (priority 0, no guard) ->",
                "t.done (ends conversation)",
                "```",
                "",
                "**Conditional Routing Example:**",
                "```",
                "d.product_choice (Decision node)",
                '  -> edge (priority 0, guard: product="A") -> q.details_A',
                '  -> edge (priority 1, guard: product="B") -> q.details_B',
                "  -> edge (priority 2, always) -> q.default",
                "```",
                "",
                "**Why Splitting Helps:**",
                "Before: q.contact with 'Name? Email? Phone?' → User confused, bot can't navigate",
                "After: q.name -> q.email -> q.phone → Clear steps, natural flow",
                "",
                "## CRITICAL INSTRUCTIONS:",
                "1. You have access to ONE TOOL: BatchFlowActionsRequest",
                "2. This tool accepts an array of actions to perform on the flow",
                "3. You must output ALL modifications in a SINGLE tool call",
                "4. NEVER make multiple tool calls - batch everything together",
                "5. Order matters - actions are executed sequentially",
                "6. Always maintain connectivity - nodes without edges are orphaned",
                "7. When deleting nodes, their edges are auto-removed",
                "8. When adding nodes, ALWAYS add edges to connect them",
                "",
                "## Action Types Available:",
                "- add_node: Add a new node to the flow",
                "- update_node: Update an existing node",
                "- delete_node: Delete a node (automatically removes its edges)",
                "- add_edge: Add a new edge between nodes",
                "- update_edge: Update an existing edge",
                "- delete_edge: Delete an edge",
                "- set_entry: Change the flow's entry point",
                "",
                "## Action Examples:",
                "```json",
                json.dumps(
                    {
                        "actions": [
                            {"action": "delete_node", "node_id": "q.old_question"},
                            {
                                "action": "add_node",
                                "node_definition": {
                                    "id": "q.new_question",
                                    "kind": "Question",
                                    "key": "answer_key",
                                    "prompt": "What is your question?",
                                },
                            },
                            {"action": "set_entry", "entry_node": "q.new_question"},
                            {
                                "action": "add_edge",
                                "source": "q.new_question",
                                "target": "q.next_node",
                                "priority": 0,
                            },
                            {
                                "action": "update_node",
                                "node_id": "q.existing",
                                "updates": {
                                    "prompt": "Updated question text",
                                    "allowed_values": ["yes", "no"],
                                },
                            },
                        ]
                    },
                    indent=2,
                ),
                "```",
                "",
                "## Important Rules:",
                "1. When deleting nodes, you don't need to delete edges - they're removed automatically",
                "2. When adding nodes, remember to connect them with edges",
                "3. Ensure node IDs are unique and meaningful (e.g., q.field_name, d.decision, t.terminal)",
                "4. Always validate that source and target nodes exist before adding edges",
                "5. Order actions correctly: delete old structure before adding new",
                "6. If deleting the entry node, update the flow's entry point to the new first node",
                "7. When splitting nodes, maintain the original flow sequence",
                "",
                "## Flow Language Reference:",
                "",
                "### Node Types:",
                "- Question: Collects information from user",
                "  - Required: id, kind='Question', key, prompt",
                "  - Optional: allowed_values, clarification, examples",
                "",
                "- Decision: Routes conversation based on logic",
                "  - Required: id, kind='Decision'",
                "  - Optional: decision_type='llm_assisted', decision_prompt",
                "",
                "- Terminal: Ends the conversation",
                "  - Required: id, kind='Terminal'",
                "  - Optional: reason, success (true/false)",
                "",
                "### Edge Properties:",
                "- source: Source node ID",
                "- target: Target node ID",
                "- priority: Lower numbers = higher priority (default 0)",
                '- guard: Condition object (e.g., {"fn": "answers_has", "args": {"key": "field"}})',
                "- condition_description: Human-readable description",
                "",
            ]
        )

        # Add simplified view context if enabled
        if simplified_view_enabled and active_path:
            lines.extend(
                [
                    "## 🎯 VIEW CONTEXT:",
                    f"- User is viewing the '{active_path}' path only",
                    "- Focus modifications on nodes related to this path",
                    "- Don't modify nodes from other conversation paths",
                    "",
                ]
            )

        # Add current flow
        lines.extend(
            [
                "## Current Flow Definition:",
                "```json",
                json.dumps(flow, indent=2),
                "```",
                "",
            ]
        )

        # Add conversation history
        if history:
            lines.extend(
                [
                    "## Conversation History:",
                ]
            )
            for msg in history:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                lines.append(f"{role.title()}: {content}")
            lines.append("")

        # Final instruction
        lines.extend(
            [
                "## Complex Transformation Examples:",
                "",
                "### Splitting Multi-Question Nodes:",
                "If user asks to split nodes with multiple questions:",
                "1. Identify nodes where prompt contains multiple '?' marks",
                "2. For each multi-question node:",
                "   - Delete the original node",
                "   - Create separate nodes for each question",
                "   - Reconnect edges to maintain flow",
                "3. Update entry point if needed",
                "",
                "Example: 'What's your name? And your email?' becomes:",
                "- q.name: 'What's your name?'",
                "- q.email: 'What's your email?'",
                "",
                "### Merging Sequential Nodes:",
                "If user asks to combine nodes:",
                "1. Create new combined node",
                "2. Delete original nodes",
                "3. Reconnect edges",
                "",
                "## Your Task:",
                "Analyze the user's request and generate the appropriate actions to modify the flow.",
                "Remember: Output ALL actions in a SINGLE BatchFlowActionsRequest tool call.",
                "Be helpful, make smart decisions, and ensure the flow remains valid.",
                "For complex transformations, think step-by-step about all required changes.",
            ]
        )

        return "\n".join(lines)

    def _log_prompt_debug(self, prompt: str, stage: str) -> None:
        """Log prompt to file in development mode."""
        try:
            import os
            import tempfile
            from datetime import datetime

            temp_dir = tempfile.gettempdir()
            debug_dir = os.path.join(temp_dir, "chatai_debug")
            os.makedirs(debug_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"llm_prompt_{stage}_{timestamp}.txt"
            filepath = os.path.join(debug_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(prompt)

            logger.info(f"Debug prompt written to {filename}")
        except Exception as e:
            logger.warning(f"Failed to write debug prompt: {e}")
