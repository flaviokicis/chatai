from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from typing import Any, NamedTuple
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.flow_modification_tools import ToolResult
from app.core.llm import LLMClient


class FlowChatResponse(NamedTuple):
    """Structured response from flow chat agent."""
    messages: list[str]
    flow_was_modified: bool
    modification_summary: str | None = None


class ToolSpec(BaseModel):
    """Specification for a callable tool."""

    name: str
    description: str | None = None
    args_schema: type[BaseModel] | None = None
    func: Callable[..., str]


class FlowChatAgent:
    """LLM-driven agent that can apply tools to modify a flow."""

    def __init__(self, llm: LLMClient, tools: Sequence[ToolSpec] | None = None) -> None:
        self.llm = llm
        self.tools = {t.name: t for t in tools or []}

    async def process(
        self,
        flow: dict[str, Any],
        history: Sequence[dict[str, str]],
        flow_id: UUID | None = None,
        session: Session | None = None,
        simplified_view_enabled: bool = False,
        active_path: str | None = None
    ) -> FlowChatResponse:
        """Process conversation and return assistant responses."""

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"FlowChatAgent.process called with flow_id={flow_id}, history_len={len(history)}")

        messages = list(history)
        outputs: list[str] = []
        flow_modified = False
        modification_details: list[str] = []

        # Create custom tool mapping to handle LangChain's class name convention
        tool_schemas = []
        schema_to_tool_map = {}  # Maps schema class name -> actual tool name

        for tool in self.tools.values():
            if tool.args_schema:
                schema_class_name = tool.args_schema.__name__  # e.g., "SetEntireFlowRequest"
                actual_tool_name = tool.name  # e.g., "set_entire_flow"

                tool_schemas.append(tool.args_schema)
                schema_to_tool_map[schema_class_name] = actual_tool_name

        logger.info(f"Available tools: {list(self.tools.keys())}")
        logger.info(f"Schema to tool mapping: {schema_to_tool_map}")
        logger.info(f"Tool schemas: {len(tool_schemas)}")

        # Simple loop allowing multiple tool invocations
        should_complete = False  # Flag to signal early completion
        validation_called = False  # Track if validation has been called to prevent duplicates
        for iteration in range(10):  # hard limit to avoid infinite loops
            logger.info(f"Agent iteration {iteration+1}: Building prompt...")
            prompt = self._build_prompt(flow, messages, simplified_view_enabled, active_path)
            logger.info(f"Agent iteration {iteration+1}: Calling LLM extract with prompt length {len(prompt)}")

            # DEVELOPMENT MODE ONLY: Write raw prompts to disk for debugging
            # This prevents disk space exhaustion and security issues in production
            from app.settings import is_development_mode
            is_development = is_development_mode()

            if is_development:
                import os
                import tempfile
                from datetime import datetime

                # Use system temp directory instead of hardcoded path
                temp_dir = tempfile.gettempdir()
                log_filename = f"llm_raw_prompt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_iter{iteration+1}.txt"
                log_path = os.path.join(temp_dir, "chatai_debug", log_filename)

                try:
                    # Ensure debug directory exists
                    os.makedirs(os.path.dirname(log_path), exist_ok=True)

                    with open(log_path, "w", encoding="utf-8") as f:
                        f.write(prompt)
                    logger.info(f"Agent iteration {iteration+1}: Raw prompt written to {log_filename} (development mode)")
                except Exception as e:
                    logger.warning(f"Failed to write debug prompt file: {e}")
            else:
                logger.debug(f"Agent iteration {iteration+1}: Prompt logging disabled in production mode")

            # Run LLM call in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.llm.extract, prompt, tool_schemas)
            content = result.get("content")
            tool_calls = result.get("tool_calls") or []

            # DEVELOPMENT MODE ONLY: Append the LLM response to debug file
            if is_development and "log_path" in locals():
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write("\n\n=== LLM RESPONSE ===\n")
                        f.write(f"Content Length: {len(content) if content else 0}\n")
                        f.write(f"Tool Calls Count: {len(tool_calls)}\n")
                        if content:
                            f.write(f"Content: {content}\n")
                        if tool_calls:
                            f.write("Tool Calls:\n")
                            for i, call in enumerate(tool_calls):
                                f.write(f"  {i+1}. {call.get('name')}: {call.get('arguments', {})}\n")
                except Exception as e:
                    logger.warning(f"Failed to append LLM response to debug file: {e}")

            logger.info(f"Agent iteration {iteration+1}: LLM returned content_len={len(content) if content else 0}, tool_calls_count={len(tool_calls)}")
            if content:
                content_preview = content[:150] + "..." if len(content) > 150 else content
                logger.info(f"Agent iteration {iteration+1}: Content preview: '{content_preview}'")
            if tool_calls:
                for i, call in enumerate(tool_calls):
                    logger.info(f"Agent iteration {iteration+1}: Tool call {i+1}: name={call.get('name')}, args_keys={list(call.get('arguments', {}).keys())}")

            # If we have tool calls, prioritize them over content
            if tool_calls:
                # Only add content if it's not a massive JSON dump
                if content and len(content) < 500 and not content.strip().startswith("{"):
                    logger.info(f"Agent iteration {iteration+1}: Adding content (not JSON dump)")
                    outputs.append(content)
                    messages.append({"role": "assistant", "content": content})
                else:
                    logger.info(f"Agent iteration {iteration+1}: Filtering out JSON dump content (len={len(content) if content else 0})")
            elif content:
                # No tool calls, so include the content
                logger.info(f"Agent iteration {iteration+1}: Adding content (no tool calls)")
                # Ensure final response is in Portuguese by prefixing a Portuguese instruction
                if iteration > 0 and len(content) > 50 and "what would you like to do next" in content.lower():
                    logger.info(f"Agent iteration {iteration+1}: Converting English response to Portuguese")
                    portuguese_content = ("Ótimo! O fluxo foi atualizado com sucesso.\n\n"
                                        "O que você gostaria de fazer agora? Posso:\n"
                                        "- Editar prompts, valores permitidos ou adicionar esclarecimentos\n"
                                        "- Adicionar novos caminhos com lógica de decisão\n"
                                        "- Ajustar regras de validação e dependências\n"
                                        "- Modificar políticas de conversação\n"
                                        "- Localizar prompts ou reorganizar estrutura\n\n"
                                        "Me diga que mudança você quer fazer!")
                    outputs.append(portuguese_content)
                    messages.append({"role": "assistant", "content": portuguese_content})
                else:
                    outputs.append(content)
                    messages.append({"role": "assistant", "content": content})

            if not tool_calls:
                logger.info(f"Agent iteration {iteration+1}: No tool calls, breaking loop")
                break

            # CRITICAL: Stop after successful modifications to prevent excessive iterations
            # The LLM should batch all operations in one response
            successful_mods = False

            # Filter out redundant validation calls - only allow one validation per session
            if validation_called:
                tool_calls = [call for call in tool_calls
                             if call.get("name") not in ["ValidateFlowRequest", "GetFlowSummaryRequest"]]
                if not tool_calls:
                    logger.info(f"Agent iteration {iteration+1}: All tool calls were redundant validations, breaking loop")
                    break
            for call in tool_calls:
                schema_name = call.get("name")  # This will be the schema class name
                actual_tool_name = schema_to_tool_map.get(schema_name, schema_name)  # Map to actual tool name
                args = call.get("arguments", {})
                tool = self.tools.get(actual_tool_name)

                if not tool:
                    logger.warning(f"Agent iteration {iteration+1}: Tool '{schema_name}' -> '{actual_tool_name}' not found in available tools")
                    continue

                logger.info(f"Agent iteration {iteration+1}: Executing tool '{schema_name}' -> '{actual_tool_name}'")

                # All tools need special handling to inject flow_definition and other context
                modification_tools = ["add_node", "update_node", "delete_node",
                                    "add_edge", "update_edge", "delete_edge"]
                read_only_tools = ["validate_flow", "get_flow_summary"]

                try:
                    is_success = False  # Initialize success flag

                    if actual_tool_name == "set_entire_flow":
                        # set_entire_flow: flow_definition is provided by LLM
                        flow_def = args.get("flow_definition", {})
                        logger.info(f"Agent iteration {iteration+1}: Calling set_entire_flow with {len(flow_def.get('nodes', []))} nodes")
                        tool_output = tool.func(flow_def, flow_id=flow_id, session=session)
                        # Update local flow if successful
                        if "✅" in str(tool_output):
                            is_success = True
                            flow = flow_def
                            flow_modified = True
                            modification_details.append("set_entire_flow: Updated complete flow definition")
                    elif actual_tool_name in modification_tools:
                        # Modification tools: inject flow as first parameter
                        logger.info(f"Agent iteration {iteration+1}: Calling '{actual_tool_name}' with args: {list(args.keys())}")
                        logger.info(f"Agent iteration {iteration+1}: Current flow has {len(flow.get('nodes', []))} nodes")

                        # Log the specific node we're trying to update (if it's update_node)
                        if actual_tool_name == "update_node" and "node_id" in args:
                            node_id = args["node_id"]
                            for node in flow.get("nodes", []):
                                if node.get("id") == node_id:
                                    logger.info(f"Agent iteration {iteration+1}: BEFORE TOOL - Node '{node_id}' current state: {node}")
                                    break

                        # Validate required parameters before calling tool
                        validation_error = self._validate_tool_parameters(actual_tool_name, args)
                        if validation_error:
                            logger.error(f"Agent iteration {iteration+1}: Parameter validation failed: {validation_error}")
                            # Add validation error to conversation for LLM to see and correct
                            error_message = f"Parameter Error: {validation_error}"
                            messages.append({"role": "system", "content": error_message})
                            continue  # Skip this tool call and let LLM retry

                        # Provide defaults for optional parameters
                        if "updates" in args and args["updates"] is None:
                            args["updates"] = {}

                        logger.info(f"Agent iteration {iteration+1}: Final args being passed: {args}")
                        logger.info(f"Agent iteration {iteration+1}: flow_id={flow_id}, session={'present' if session else 'None'}")

                        # Call with flow_definition as first parameter
                        tool_output = tool.func(flow, **args, flow_id=flow_id, session=session)

                        logger.info(f"Agent iteration {iteration+1}: Tool '{actual_tool_name}' completed with output: {tool_output}")

                        # ⚠️ Use structured tool responses instead of hacky string parsing!

                        # Check if we got a structured ToolResult
                        if isinstance(tool_output, ToolResult):
                            is_success = tool_output.success

                            # Signal completion when validation tools are called after modifications
                            if (tool_output.is_validation and flow_modified and
                                tool_output.success and not tool_output.should_continue):
                                logger.info(f"Agent iteration {iteration+1}: Validation tool after modifications signals completion")
                                should_complete = True
                                break  # Exit tool call loop - agent finished validating completed work
                        else:
                            # Legacy string-based detection (for backward compatibility with other tools)
                            tool_output_str = str(tool_output)
                            success_indicators = ["✅", "Added", "Updated", "Deleted"]
                            error_indicators = ["Failed", "Error", "not found", "missing"]
                            is_success = (
                                any(indicator in tool_output_str for indicator in success_indicators) and
                                not any(error in tool_output_str for error in error_indicators)
                            )

                        if is_success:
                            logger.info(f"Agent iteration {iteration+1}: Tool reported success, reloading flow from database for next tool")

                            # Track successful modifications using structured result
                            if isinstance(tool_output, ToolResult) and tool_output.is_modification:
                                flow_modified = True
                                successful_mods = True  # Mark successful modification
                                modification_details.append(f"{tool_output.action}: - Alterações aplicadas")
                            elif actual_tool_name in modification_tools:  # Legacy for non-ToolResult responses
                                flow_modified = True
                                successful_mods = True  # Mark successful modification
                                node_id = args.get("node_id", "")
                                edge_info = f"{args.get('source', '')}->{args.get('target', '')}" if args.get("source") and args.get("target") else ""
                                modification_details.append(f"{actual_tool_name}: {node_id}{edge_info} - Alterações aplicadas")

                                # Add context message to help LLM remember what it just did
                                if actual_tool_name == "add_node" and args.get("node_definition"):
                                    node_def = args["node_definition"]
                                    context_msg = f"✅ I just successfully added new {node_def.get('kind', 'node')} '{node_def.get('id', 'unknown')}' with prompt: '{node_def.get('prompt', 'N/A')}' - this is a new node that I created."
                                    messages.append({"role": "system", "content": context_msg})

                            # Reload the flow from database to get the cumulative changes for next tool call
                            from app.db.repository import get_flow_by_id
                            updated_flow_db = get_flow_by_id(session, flow_id)
                            if updated_flow_db:
                                flow = updated_flow_db.definition  # Update flow for next tool call
                                logger.info(f"Agent iteration {iteration+1}: Reloaded flow from DB version {updated_flow_db.version}")

                                # Verify the node was updated correctly
                                if actual_tool_name == "update_node" and "node_id" in args:
                                    node_id = args["node_id"]
                                    for node in flow.get("nodes", []):
                                        if node.get("id") == node_id:
                                            logger.info(f"Agent iteration {iteration+1}: VERIFIED - Node '{node_id}' after reload: {node}")
                                            break
                            else:
                                logger.error(f"Agent iteration {iteration+1}: Failed to reload flow from database!")
                        else:
                            logger.warning(f"Agent iteration {iteration+1}: Tool '{actual_tool_name}' did not report success: {tool_output}")
                    elif actual_tool_name in read_only_tools:
                        # Read-only tools: inject flow as the flow_definition parameter
                        logger.info(f"Agent iteration {iteration+1}: Calling '{actual_tool_name}'")
                        tool_output = tool.func(flow)

                        # Track validation calls to prevent redundant ones
                        if actual_tool_name in ["validate_flow", "get_flow_summary"]:
                            validation_called = True
                    else:
                        # Unknown tool, call as-is
                        logger.info(f"Agent iteration {iteration+1}: Calling tool '{actual_tool_name}' with args: {list(args.keys())}")
                        tool_output = tool.func(**args)
                except TypeError as e:
                    logger.error(f"Agent iteration {iteration+1}: Tool '{actual_tool_name}' failed: {e}")
                    # Provide helpful error message with context for re-prompting
                    if "missing" in str(e) and "required" in str(e):
                        # Extract the missing parameter name and provide context
                        error_msg = str(e)
                        if "node_definition" in error_msg:
                            tool_output = f"Error: {actual_tool_name} requires a complete 'node_definition' parameter. Please provide the full node object with id, kind, and other required properties. {error_msg}"
                        elif "updates" in error_msg:
                            tool_output = f"Error: {actual_tool_name} requires an 'updates' parameter with the fields to modify. For example: updates={{'prompt': 'new text'}}. {error_msg}"
                        elif "flow_definition" in error_msg:
                            tool_output = f"Error: {actual_tool_name} requires a complete flow definition as JSON. {error_msg}"
                        else:
                            tool_output = f"Error: {actual_tool_name} is missing required arguments. {error_msg}. Check the tool schema and provide all required parameters."
                    else:
                        tool_output = f"Tool call failed: {actual_tool_name}. Error: {e!s}"

                    # Add error message to conversation for LLM to see and correct
                    error_message = f"Tool Error: {tool_output}"
                    messages.append({"role": "system", "content": error_message})
                    logger.info(f"Agent iteration {iteration+1}: Added tool error to conversation for re-prompting: {error_message}")

                except Exception as e:
                    logger.error(f"Agent iteration {iteration+1}: Tool '{actual_tool_name}' unexpected error: {e}")
                    tool_output = f"Unexpected error calling {actual_tool_name}: {e!s}"

                    # Add error message to conversation for LLM to see and correct
                    error_message = f"Tool Error: {tool_output}"
                    messages.append({"role": "system", "content": error_message})
                    logger.info(f"Agent iteration {iteration+1}: Added unexpected error to conversation for re-prompting: {error_message}")

                logger.info(f"Agent iteration {iteration+1}: Tool '{actual_tool_name}' returned: '{tool_output}'")

                # Only add success messages to conversation, errors are already added above
                if isinstance(tool_output, ToolResult):
                    if tool_output.success and tool_output.is_modification:
                        messages.append({"role": "assistant", "content": f"{tool_output.action} completed successfully. Flow has been updated."})
                    elif tool_output.success:
                        messages.append({"role": "assistant", "content": f"Tool {tool_output.action} executed successfully."})
                    # Don't add error messages here - they're already added in the except blocks above
                elif is_success and actual_tool_name in modification_tools:
                    # Legacy support for non-ToolResult responses
                    messages.append({"role": "assistant", "content": f"{actual_tool_name} completed successfully. Flow has been updated."})
                elif is_success:
                    # Read-only tools or other successful operations
                    messages.append({"role": "assistant", "content": f"Tool {actual_tool_name} executed successfully."})
                # Don't add generic messages for failures - let the error handling above provide context

            # Check if we should complete after this iteration
            if should_complete:
                logger.info(f"Agent iteration {iteration+1}: Early completion triggered by validation after modifications")
                break

            # Prevent runaway iterations with reasonable limit, but allow more iterations for error recovery
            if iteration >= 5:  # Allow more iterations for error recovery and complex operations
                logger.info(f"Agent iteration {iteration+1}: Reached iteration limit, stopping")
                break

        # Create modification summary
        modification_summary = None
        if modification_details:
            modification_summary = "; ".join(modification_details)

        # Create meaningful final message
        if flow_modified:
            # Look for meaningful LLM content that explains what was done
            meaningful_outputs = [out for out in outputs if out and len(out) > 30 and
                                not out.startswith("Tool ") and
                                "completed successfully" not in out and
                                not out.startswith("✅ Fluxo atualizado")]

            if meaningful_outputs:
                # Use the LLM's own description of what it did
                last_meaningful = meaningful_outputs[-1]
                if "Como posso" not in last_meaningful and "What would you like" not in last_meaningful:
                    outputs = [last_meaningful]
                else:
                    outputs = ["✅ Alterações aplicadas no fluxo com sucesso!"]
            else:
                outputs = ["✅ Alterações aplicadas no fluxo com sucesso!"]
        elif outputs:
            # If no modifications but there are outputs, use the last meaningful content
            meaningful_outputs = [out for out in outputs if out and len(out) > 10 and not out.startswith("Tool ")]
            if meaningful_outputs:
                outputs = [meaningful_outputs[-1]]  # Keep only the last meaningful output
            else:
                outputs = ["Como posso te ajudar com o fluxo?"]
        else:
            outputs = ["Como posso te ajudar com o fluxo?"]

        logger.info(f"FlowChatAgent.process complete: returning {len(outputs)} outputs, flow_modified={flow_modified}")
        if flow_modified:
            logger.info(f"Flow modifications: {modification_summary}")

        return FlowChatResponse(
            messages=outputs,
            flow_was_modified=flow_modified,
            modification_summary=modification_summary
        )

    def _build_prompt(
        self,
        flow: dict[str, Any],
        history: Sequence[dict[str, str]],
        simplified_view_enabled: bool = False,
        active_path: str | None = None
    ) -> str:
        """Comprehensive prompt builder for flow editing with examples and guidance."""

        lines = []

        # Main role and capabilities
        lines.extend([
            "You are an expert flow editing assistant specialized in creating and modifying conversational flows.",
            "You can help users create, modify, and optimize conversation flows using our JSON-based flow language.",
            "",
            "## Your Capabilities:",
            "- Create complete flows from scratch based on user descriptions",
            "- Modify existing flows by adding, editing, or removing nodes and edges",
            "- Set up proper flow structure with entry points, nodes, edges, and terminals",
            "- Create subgraphs for organizing complex conversation paths",
            "- Add decision logic and guards for intelligent flow navigation",
            "- Configure policies for conversation management",
            "",
        ])

        # Flow language documentation
        lines.extend([
            "## Flow Language Overview:",
            "",
            "### Node Types:",
            "- **Question**: Asks user for information, stores in `answers[key]`",
            '  - Required: `id`, `kind: "Question"`, `key`, `prompt`',
            "  - Optional: `allowed_values`, `clarification`, `examples`, `dependencies`",
            "",
            "- **Decision**: Routes conversation based on logic",
            '  - Required: `id`, `kind: "Decision"`',
            '  - Optional: `decision_type: "llm_assisted"`, `decision_prompt`',
            "",
            "- **Terminal**: Ends the conversation",
            '  - Required: `id`, `kind: "Terminal"`',
            "  - Optional: `reason`, `success: true/false`",
            "",
            "### Edges:",
            "Connect nodes with optional guards and priorities:",
            "- `source`: starting node id",
            "- `target`: destination node id",
            "- `priority`: lower numbers evaluated first",
            '- `guard`: conditions like `{"fn": "answers_has", "args": {"key": "field_name"}}`',
            "- `condition_description`: human-readable condition explanation",
            "",
        ])

        # Subgraphs explanation with example
        lines.extend([
            "## Subgraphs (Advanced Paths):",
            "Subgraphs let you create specialized conversation paths that branch from main flow.",
            "Each subgraph handles a specific scenario with its own questions, then returns to global flow.",
            "",
            "### When to Use Subgraphs:",
            "- Different product/service categories need different questions",
            "- Emergency vs. routine cases require different handling",
            "- Complex scenarios need specialized question sequences",
            "",
            "### Subgraph Pattern:",
            "1. Main flow has decision node that routes to different paths",
            "2. Each path becomes a subgraph with specialized questions",
            "3. All subgraphs eventually lead to common global questions",
            "4. Flow ends at shared terminal nodes",
            "",
        ])

        # Dentist flow example
        lines.extend([
            "## Complete Example - Dentist Office Flow:",
            "This example shows how to structure a complex multi-path flow with subgraphs:",
            "",
            "```json",
            json.dumps(self._get_dentist_flow_example(), indent=2),
            "```",
            "",
            "### Key Patterns in This Example:",
            "1. **Entry Point**: `q.motivo_consulta` asks initial open question",
            "2. **Main Decision**: `d.triagem_inicial` routes to 4 different paths:",
            "   - Routine cleaning (limpeza/rotina)",
            "   - Emergency/pain (emergência/dor)",
            "   - Orthodontics (ortodontia)",
            "   - Specific procedures (outros procedimentos)",
            "3. **Subgraphs**: Each path has specialized questions for that scenario",
            "4. **Convergence**: All paths eventually lead to global questions:",
            "   - `q.plano_saude` (insurance)",
            "   - `q.urgencia_atendimento` (urgency)",
            "   - `q.horario_preferencia` (preferred time)",
            "   - `q.contato_paciente` (contact info)",
            "5. **Smart Terminals**: Final terminal chosen based on which path was taken",
            "",
        ])

        # Instructions
        lines.extend([
            "## Instructions:",
            "- **CRITICAL: ALWAYS use tools - NEVER output flow JSON directly to the user!**",
            "- **SCHEMA VERSION: ALL flows must use schema_version 'v1'**",
            "- **BIAS TO ACTION**: When user requests a change, just do it directly - don't ask for confirmation",
            "- **SIMPLE CHANGES**: For simple requests like adding nodes or questions, use add_node/update_node tools instead of set_entire_flow",
            "- **SIMPLE OPERATIONS = BATCH IN ONE RESPONSE**:",
            "  - Deleting nodes/edges, updating prompts, reconnecting flows → Do ALL at once",
            "  - Example: Remove question = delete_node + reconnect edges in ONE response",
            "  - **Don't** delete one node, wait, then delete another - batch them!",
            "- **COMPLEX OPERATIONS = Multiple iterations OK**:",
            "  - Creating entire new subpaths, major restructuring, complex logic changes",
            "  - You can think step-by-step and iterate for truly complex reasoning",
            "- **CRITICAL: TOOL CALL ORDER MATTERS** - When making multiple tool calls, order them correctly!",
            "  - BEFORE deleting nodes: delete all edges connected to them first",
            "  - BEFORE adding edges: ensure both source and target nodes exist",
            "  - BEFORE updating nodes: make sure the node exists",
            "  - Example order: delete_edge → delete_node → add_node → add_edge",
            "",
            "## Node Selection Guide:",
            "- **Question Node**: Use when collecting information from user (name, preferences, yes/no answers)",
            "  - Example: \"What's your name/phone number/email?\", \"Do you prefer card or cash?\", \"What's your phone number?\"",
            "  - ALWAYS use Question for data collection, even if the answer affects routing later",
            "- **Decision Node**: Use ONLY when routing between different subpaths/workflows",
            '  - Example: After collecting "service type", route to dental vs orthodontics vs emergency workflows',
            '  - Example: After collecting "urgency level", route to urgent vs routine handling workflows',
            "  - Decision nodes are invisible - they just branch the conversation to different question sets",
            "- **SIMPLE RULE**: Need info from user? → Question. Need to branch to different workflows? → Decision.",
            "- **Most flows don't need Decision nodes** - just Questions leading to more Questions!",
            "",
            "## CRITICAL: Removing Questions/Nodes:",
            '- **When user says "remove a question"** → YOU MUST DELETE THE NODE, not just edges!',
            "- **STEP 1**: Find the node by searching through ALL nodes in the flow definition",
            "- **STEP 2**: Look at each node's `prompt` field to match user's description",
            "- **STEP 3**: Use `delete_node` with the correct `node_id` to remove the entire question",
            "- **STEP 4**: The `delete_node` tool will automatically handle connected edges",
            "- **WRONG**: Only calling `delete_edge` - this leaves the question in the flow!",
            "- **RIGHT**: Call `delete_node` to completely remove the question",
            "- **NEVER modify nodes the user didn't ask about**",
            "",
            "## Completion Instructions:",
            "- **CRITICAL: DO THE WORK, DON'T JUST EXPLAIN IT**: If user asks for changes, USE TOOLS immediately!",
            '  - **WRONG**: "I can remove that question for you..." (just explaining)',
            "  - **RIGHT**: Call delete_node tool to actually remove it, THEN explain what you did",
            "- **For SIMPLE requests** (delete node, update prompt, reconnect):",
            "  - Batch all operations in ONE response to be efficient",
            "  - Example: 'remove question' = delete_node + reconnect edges in one response",
            "- **For COMPLEX requests** (create subpaths, major restructuring):",
            "  - You can use multiple iterations and think step-by-step if needed",
            "- **DO NOT** call validate_flow unless there's a specific validation concern",
            "- **DO NOT** call get_flow_summary unless user specifically asks for a summary",
            "",
            "### Tool Usage Examples:",
            "**EFFICIENT: Multiple operations in one response (ORDERED):**",
            "",
            '**Example: User asks "Remove the payment question" (single node):**',
            "1. Find the node with payment-related `prompt` text",
            "2. Call `delete_node` with that node's ID - this removes the question AND its edges",
            "3. Done! (delete_node handles everything automatically)",
            "",
            '**Example: User asks "Remove covered/uncovered questions" (multiple nodes):**',
            "1. Find ALL nodes related to coverage (questions, decisions, etc.)",
            "2. Call `delete_node` for node1, `delete_node` for node2, `delete_node` for node3 - ALL in the SAME response!",
            "3. Done! Don't wait between deletions - batch them all together!",
            "",
            '**Example: User asks "Remove payment question and connect address to phone":**',
            "1. Call `delete_node` to remove payment question (handles its edges automatically)",
            "2. Call `add_edge` to create new connection from address to phone",
            "- All in the SAME response, in the CORRECT ORDER, not separate iterations!",
            "",
            "**Adding a question:**",
            "```",
            "add_node:",
            "  node_definition:",
            '    id: "q.new_question"',
            '    kind: "Question"',
            '    key: "new_question"',
            '    prompt: "What is your question?"',
            "```",
            "",
            "**Adding a decision (for routing logic only):**",
            "```",
            "add_node:",
            "  node_definition:",
            '    id: "d.service_routing"',
            '    kind: "Decision"',
            '    label: "Route by service type"',
            '    decision_type: "llm_assisted"',
            '    decision_prompt: "Route different service types to their appropriate question sets"',
            "```",
            "",
            "**Adding an edge:**",
            "```",
            "add_edge:",
            '  source: "q.source_node"',
            '  target: "q.target_node"',
            "  priority: 0",
            '  condition_description: "Description of when this path is taken"',
            "```",
            "",
            "- **TOOL REQUIREMENTS: Always provide ALL required parameters**",
            "  - add_node: requires node_definition (complete node object)",
            "  - update_node: requires node_id AND updates (dict)",
            "  - add_edge: requires source AND target",
            "  - update_edge: requires source, target AND updates (dict)",
            "  - set_entire_flow: requires complete flow_definition (dict)",
            "- **ABSOLUTELY FORBIDDEN: Outputting raw JSON to user** - always use appropriate tools",
            "- Use meaningful IDs: `q.field_name` for questions, `d.description` for decisions, `t.outcome` for terminals",
            "- Include `condition_description` on edges to explain routing logic",
            "- Set up proper priorities on edges (lower numbers = higher priority)",
            "",
            "## When User Provides WhatsApp Conversation:",
            "1. Analyze the conversation flow and identify main paths/scenarios",
            "2. Extract key questions that need to be asked",
            "3. Identify decision points where conversation branches",
            "4. Create appropriate subgraphs for different scenarios",
            "5. Set up global questions that apply to all paths",
            "6. Use `set_entire_flow` tool to create the complete flow when needed (creating a new one from scratch) (NEVER output JSON directly). For punctual changes, use the other tools.",
            "",
        ])

        # Current state
        lines.extend([
            "## Current Flow:",
            "```json",
            f"{json.dumps(flow, indent=2) if flow else 'null'}",
            "```",
            "",
        ])

        # Add frontend context if simplified view is enabled
        logger = logging.getLogger(__name__)
        logger.info(f"_build_prompt: simplified_view_enabled={simplified_view_enabled}, active_path='{active_path}'")

        if simplified_view_enabled and active_path:
            # Find nodes that belong to this specific path
            try:
                path_nodes = self._get_path_specific_nodes(flow, active_path)
                path_node_list = ", ".join(path_nodes) if path_nodes else "none found"
                logger.info(f"_build_prompt: Adding focused view context for '{active_path}' with nodes: {path_node_list}")

                lines.extend([
                    "## 🎯 CRITICAL: User's Current View Context",
                    f"- **SIMPLIFIED VIEW ACTIVE** - User can ONLY see the '{active_path}' conversation path",
                    f"- **Path-specific nodes visible to user**: {path_node_list}",
                    f"- **GOLDEN RULE: ONLY modify nodes that belong to '{active_path}' path**",
                    "- **FORBIDDEN: Do NOT touch nodes from other paths** - user can't see them!",
                    f"- **When user says 'remove a question', they mean from the '{active_path}' path ONLY**",
                    f"- **If no relevant nodes found in '{active_path}' path, ask for clarification**",
                    "",
                    f"## How to Identify '{active_path}' Path Nodes:",
                    f"1. Look for nodes whose prompts/content relate to '{active_path.lower()}'",
                    f"2. Trace edges from decision nodes that route to '{active_path}' scenarios",
                    f"3. Check node IDs that contain keywords like '{active_path.lower().replace(' ', '_')}'",
                    "4. **NEVER modify nodes clearly belonging to other conversation paths**",
                    "",
                ])
            except Exception as e:
                import traceback
                logger.error(f"_build_prompt: Failed to get path-specific nodes for '{active_path}': {e}")
                logger.error(f"_build_prompt: Full traceback: {traceback.format_exc()}")
                logger.error(f"_build_prompt: Flow structure - nodes type: {type(flow.get('nodes', {}))}, edges_from type: {type(flow.get('edges_from', {}))}")
                if flow.get("edges_from"):
                    first_key = next(iter(flow["edges_from"]))
                    first_edges = flow["edges_from"][first_key]
                    logger.error(f"_build_prompt: Sample edge structure: {type(first_edges)} = {first_edges[:1] if first_edges else []}")

                # Fallback to no path filtering
                logger.info("_build_prompt: Falling back to full flow view due to error")
                lines.extend([
                    "## ⚠️ IMPORTANT: Frontend View Context (Error in path detection)",
                    f"- **User is viewing simplified view for '{active_path}' but path detection failed**",
                    f"- **Please be extra careful to only modify nodes related to '{active_path}'**",
                    f"- **When user asks to remove/modify, focus on '{active_path}' related content only**",
                    "",
                ])
        elif simplified_view_enabled:
            logger.info("_build_prompt: Simplified view enabled but no active_path provided")
            lines.extend([
                "## 🎯 IMPORTANT: Frontend View Context",
                "- **Simplified view is ENABLED** but no specific path selected",
                "- **Ask user to specify which path they're referring to** if their request is ambiguous",
                "",
            ])
        else:
            logger.info("_build_prompt: No simplified view context added - using full flow view")

        # Conversation history
        if history:
            lines.append("## Conversation History:")
            for m in history:
                lines.append(f"{m['role'].title()}: {m['content']}")
            lines.append("")

        lines.append("How can I help you modify or create your flow?")

        return "\n".join(lines)

    def _get_path_specific_nodes(self, flow: dict[str, Any], active_path: str) -> list[str]:
        """Use the same algorithm as frontend to find nodes for a specific path."""
        logger = logging.getLogger(__name__)

        if not flow or not active_path:
            return []

        # Replicate frontend's computePath algorithm exactly
        nodes_dict = flow.get("nodes", {})
        edges_from = flow.get("edges_from", {})
        entry = flow.get("entry")

        if not entry:
            logger.info("_get_path_specific_nodes: No entry node found in flow")
            return []

        # Step 1: Find first decision node (same as frontend's findFirstBranchDecision)
        first_decision = self._find_first_branch_decision(flow)
        if not first_decision:
            logger.info("_get_path_specific_nodes: No branching decision found, using keyword fallback")
            # FALLBACK: Just find nodes that match the path keywords
            return self._fallback_path_detection(flow, active_path)

        # Step 2: Find which outgoing edge matches the active_path
        outgoing = self._sorted_outgoing(flow, first_decision)
        target_edge = None

        logger.info(f"_get_path_specific_nodes: Checking {len(outgoing)} outgoing edges from decision {first_decision}")
        logger.info(f"_get_path_specific_nodes: First edge structure: {outgoing[0] if outgoing else 'None'}")

        for i, edge in enumerate(outgoing):
            # Handle both dict and list edge formats
            if isinstance(edge, dict):
                condition_desc = edge.get("condition_description", "")
                label = edge.get("label", "")
                target = edge.get("target")
            elif isinstance(edge, list) and len(edge) >= 2:
                # Assume [source, target, label, condition_desc] or similar format
                target = edge[1] if len(edge) > 1 else ""
                label = edge[2] if len(edge) > 2 else ""
                condition_desc = edge[3] if len(edge) > 3 else ""
            else:
                logger.warning(f"_get_path_specific_nodes: Unknown edge format: {edge}")
                continue

            logger.info(f"_get_path_specific_nodes: Edge {i}: target={target}, label='{label}', condition='{condition_desc}'")

            # Check if this edge matches the active path
            if (active_path.lower() in condition_desc.lower() or
                active_path.lower() in label.lower() or
                condition_desc.lower() in active_path.lower() or
                label.lower() in active_path.lower()):
                target_edge = {"target": target, "label": label, "condition_description": condition_desc}
                logger.info(f"_get_path_specific_nodes: Found matching edge for path '{active_path}': {target_edge}")
                break

        if not target_edge:
            logger.info(f"_get_path_specific_nodes: No edge found matching path '{active_path}'")
            return []

        # Step 3: Create branch selection (same as frontend)
        target_node_id = target_edge["target"]  # We created this as a dict above
        branch_selection = {first_decision: target_node_id}

        logger.info(f"_get_path_specific_nodes: Created branch selection: {branch_selection}")

        # Step 4: Run computePath algorithm (exact copy of frontend logic)
        path_nodes = self._compute_path(flow, branch_selection)

        logger.info(f"_get_path_specific_nodes: Found {len(path_nodes)} nodes for path '{active_path}': {path_nodes}")
        return path_nodes

    def _find_first_branch_decision(self, flow: dict[str, Any]) -> str | None:
        """Find first decision node with multiple outgoing edges (copy of frontend logic)."""
        logger = logging.getLogger(__name__)

        entry = flow.get("entry")
        if not entry:
            return None

        queue = [entry]
        visited = set()

        # Handle both list and dict formats for nodes
        nodes_data = flow.get("nodes", [])
        if isinstance(nodes_data, list):
            # Convert list to dict for easier lookup
            nodes_dict = {node.get("id"): node for node in nodes_data if node.get("id")}
            logger.info(f"_find_first_branch_decision: Converted {len(nodes_data)} nodes from list to dict format")
        else:
            nodes_dict = nodes_data

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            node = nodes_dict.get(current)
            if not node:
                continue

            outgoing = flow.get("edges_from", {}).get(current, [])
            if node.get("kind") == "Decision" and len(outgoing) > 1:
                return current

            # Add targets to queue
            for edge in outgoing:
                if isinstance(edge, dict):
                    target = edge.get("target")
                elif isinstance(edge, list) and len(edge) > 1:
                    target = edge[1]
                else:
                    target = None

                if target:
                    queue.append(target)

        return None

    def _sorted_outgoing(self, flow: dict[str, Any], node_id: str) -> list[dict]:
        """Get outgoing edges sorted by order (copy of frontend logic)."""
        edges = flow.get("edges_from", {}).get(node_id, [])
        # Handle both dict and list edge formats for sorting
        def get_order(e):
            if isinstance(e, dict):
                return e.get("order", 0)
            if isinstance(e, list) and len(e) > 4:
                # Assume order might be at index 4 or later, default to 0
                return e[4] if len(e) > 4 and isinstance(e[4], (int, float)) else 0
            return 0

        return sorted(edges, key=get_order)

    def _compute_path(self, flow: dict[str, Any], branch_selection: dict[str, str], max_steps: int = 200) -> list[str]:
        """Exact copy of frontend's computePath algorithm."""
        nodes = []
        current = flow.get("entry")
        steps = 0
        visited = set()

        # Handle both list and dict formats for nodes
        nodes_data = flow.get("nodes", [])
        if isinstance(nodes_data, list):
            # Convert list to dict for easier lookup
            nodes_dict = {node.get("id"): node for node in nodes_data if node.get("id")}
        else:
            nodes_dict = nodes_data

        while current and steps < max_steps:
            nodes.append(current)
            visited.add(current)

            outgoing = self._sorted_outgoing(flow, current)
            if not outgoing:
                break

            chosen = None
            node = nodes_dict.get(current, {})

            if node.get("kind") == "Decision" and len(outgoing) > 1:
                # Decision node - use branch selection
                preferred_target = branch_selection.get(current)
                chosen = None
                for e in outgoing:
                    e_target = e.get("target") if isinstance(e, dict) else (e[1] if isinstance(e, list) and len(e) > 1 else "")
                    if e_target == preferred_target:
                        chosen = e
                        break
                if not chosen:
                    chosen = outgoing[0]
            else:
                # Linear path - take first edge
                chosen = outgoing[0]

            if not chosen:
                break

            # Extract target from chosen edge (handle both dict and list formats)
            if isinstance(chosen, dict):
                current = chosen.get("target")
            elif isinstance(chosen, list) and len(chosen) > 1:
                current = chosen[1]
            else:
                break
            steps += 1

            # Guard against cycles
            if current in visited and steps > 2:
                break

        return nodes

    def _fallback_path_detection(self, flow: dict[str, Any], active_path: str) -> list[str]:
        """Fallback method to find path nodes when there's no clear branching decision."""
        logger = logging.getLogger(__name__)

        # Extract keywords from the active path
        keywords = active_path.lower().replace("/", " ").split()
        path_nodes = []

        # Handle both list and dict formats for nodes
        nodes_data = flow.get("nodes", [])
        if isinstance(nodes_data, list):
            for node in nodes_data:
                node_id = node.get("id", "").lower()
                node_prompt = node.get("prompt", "").lower()
                node_label = node.get("label", "").lower()

                # Check if any keyword matches
                for keyword in keywords:
                    if (keyword in node_id or
                        keyword in node_prompt or
                        keyword in node_label):
                        path_nodes.append(node.get("id"))
                        break

        logger.info(f"_fallback_path_detection: Found {len(path_nodes)} nodes with keywords from '{active_path}'")
        return path_nodes

    def _validate_tool_parameters(self, tool_name: str, args: dict[str, Any]) -> str | None:
        """Validate that required parameters are present for tool calls.
        
        Returns None if valid, error message string if invalid.
        """
        # Define required parameters for each tool
        required_params = {
            "add_node": ["node_definition"],
            "update_node": ["node_id", "updates"],
            "delete_node": ["node_id"],
            "add_edge": ["source", "target"],
            "update_edge": ["source", "target", "updates"],
            "delete_edge": ["source", "target"]
        }

        # Check if tool has required parameters defined
        if tool_name not in required_params:
            return None  # No validation needed for this tool

        # Check each required parameter
        missing_params = []
        for param in required_params[tool_name]:
            if param not in args or args[param] is None:
                missing_params.append(param)

        if missing_params:
            # Provide specific guidance based on the tool and missing parameters
            if tool_name == "add_node" and "node_definition" in missing_params:
                return (f"Tool '{tool_name}' requires a 'node_definition' parameter. "
                       "Please provide a complete node object with 'id', 'kind', and other properties. "
                       f"Example: node_definition={{'id': 'q.new_question', 'kind': 'Question', 'key': 'answer_key', 'prompt': 'Your question?'}}")
            if tool_name == "update_node" and "updates" in missing_params:
                return (f"Tool '{tool_name}' requires an 'updates' parameter. "
                       "Please provide the fields to update as a dictionary. "
                       f"Example: updates={{'prompt': 'New question text', 'allowed_values': ['yes', 'no']}}")
            return f"Tool '{tool_name}' is missing required parameters: {', '.join(missing_params)}"

        return None  # All required parameters are present

    def _build_final_message_prompt(self, messages: list[dict[str, str]]) -> str:
        """Build prompt for generating final user-friendly message after tool execution."""
        recent_messages = messages[-3:] if len(messages) >= 3 else messages

        lines = [
            "Based on the recent conversation and tool results below, provide a brief, friendly message to the user in Portuguese.",
            "Keep it under 50 words. Focus on what was accomplished, not technical details.",
            "",
            "Recent conversation:"
        ]

        for msg in recent_messages:
            lines.append(f"{msg['role'].title()}: {msg['content'][:200]}...")

        lines.extend([
            "",
            "Provide a concise, friendly response:"
        ])

        return "\n".join(lines)

    def _get_dentist_flow_example(self) -> dict[str, Any]:
        """Return the dentist flow example for prompt context."""
        return {
            "schema_version": "v1",
            "id": "flow.consultorio_dentista",
            "entry": "q.motivo_consulta",
            "metadata": {
                "name": "Consultório Dentista",
                "description": "Fluxo de atendimento para consultório odontológico"
            },
            "nodes": [
                {"id": "q.motivo_consulta", "kind": "Question", "key": "motivo_consulta", "prompt": "Olá! Bem-vindo ao nosso consultório. Como posso te ajudar hoje?"},
                {"id": "d.triagem_inicial", "kind": "Decision", "decision_type": "llm_assisted", "decision_prompt": "Com base no que o paciente descreveu, qual o melhor caminho: limpeza/rotina, emergência/dor, ortodontia, ou outros procedimentos?"},

                # Routine cleaning path
                {"id": "q.ultima_limpeza", "kind": "Question", "key": "ultima_limpeza", "prompt": "Quando foi sua última limpeza dental?", "allowed_values": ["menos de 6 meses", "6 meses a 1 ano", "mais de 1 ano", "nunca fiz"]},
                {"id": "d.situacao_higiene", "kind": "Decision", "decision_type": "llm_assisted", "decision_prompt": "Com base na última limpeza, determinar se é caso de limpeza simples, tratamento de gengiva, ou prevenção intensiva"},
                {"id": "q.limpeza_simples_motivo", "kind": "Question", "key": "limpeza_simples_motivo", "prompt": "Além da limpeza, há algo específico que te incomoda nos dentes?"},

                # Emergency path
                {"id": "q.intensidade_dor", "kind": "Question", "key": "intensidade_dor", "prompt": "Em uma escala de 1 a 10, qual a intensidade da sua dor?", "allowed_values": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]},
                {"id": "d.nivel_emergencia", "kind": "Decision", "decision_type": "llm_assisted", "decision_prompt": "Com base na intensidade da dor, determinar se é emergência imediata (dor 8-10), urgente (dor 5-7), ou pode aguardar agendamento (dor 1-4)"},
                {"id": "q.disponibilidade_hoje", "kind": "Question", "key": "disponibilidade_hoje", "prompt": "Você pode vir ao consultório agora? Temos um encaixe disponível."},

                # Global questions (all paths lead here)
                {"id": "q.plano_saude", "kind": "Question", "key": "plano_saude", "prompt": "Você tem plano odontológico ou pagará particular?", "allowed_values": ["plano odontológico", "particular"]},
                {"id": "q.contato_paciente", "kind": "Question", "key": "contato_paciente", "prompt": "Qual o melhor telefone para entrarmos em contato?"},

                # Terminals
                {"id": "t.agendamento_rotina", "kind": "Terminal", "reason": "Consulta de rotina agendada com sucesso"},
                {"id": "t.emergencia_encaminhada", "kind": "Terminal", "reason": "Emergência direcionada para atendimento imediato"}
            ],
            "edges": [
                {"source": "q.motivo_consulta", "target": "d.triagem_inicial", "guard": {"fn": "answers_has", "args": {"key": "motivo_consulta"}}, "priority": 0},

                # Main decision routing
                {"source": "d.triagem_inicial", "target": "q.ultima_limpeza", "guard": {"fn": "always", "args": {"if": "paciente quer limpeza ou consulta de rotina"}}, "priority": 0, "condition_description": "Caminho: limpeza/rotina"},
                {"source": "d.triagem_inicial", "target": "q.intensidade_dor", "guard": {"fn": "always", "args": {"if": "paciente tem dor ou emergência dental"}}, "priority": 1, "condition_description": "Caminho: emergência/dor"},

                # Routine path
                {"source": "q.ultima_limpeza", "target": "d.situacao_higiene", "priority": 0},
                {"source": "d.situacao_higiene", "target": "q.limpeza_simples_motivo", "guard": {"fn": "always", "args": {"if": "limpeza recente, caso simples"}}, "priority": 0},
                {"source": "q.limpeza_simples_motivo", "target": "q.plano_saude", "priority": 0},

                # Emergency path
                {"source": "q.intensidade_dor", "target": "d.nivel_emergencia", "priority": 0},
                {"source": "d.nivel_emergencia", "target": "q.disponibilidade_hoje", "guard": {"fn": "always", "args": {"if": "dor alta 8-10, emergência imediata"}}, "priority": 0},
                {"source": "q.disponibilidade_hoje", "target": "q.plano_saude", "priority": 0},

                # Global flow
                {"source": "q.plano_saude", "target": "q.contato_paciente", "priority": 0},

                # Terminals based on path taken
                {"source": "q.contato_paciente", "target": "t.agendamento_rotina", "guard": {"fn": "answers_has", "args": {"key": "ultima_limpeza"}}, "priority": 0},
                {"source": "q.contato_paciente", "target": "t.emergencia_encaminhada", "guard": {"fn": "answers_has", "args": {"key": "intensidade_dor"}}, "priority": 1}
            ]
        }
