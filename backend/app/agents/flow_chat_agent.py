from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Sequence, NamedTuple
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

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
            
            # Write the raw prompt exactly as sent to LLM (no formatting)
            import os
            from datetime import datetime
            log_filename = f"llm_raw_prompt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_iter{iteration+1}.txt"
            log_path = os.path.join("/Users/jessica/me/chatai", log_filename)
            try:
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(prompt)
                logger.info(f"Agent iteration {iteration+1}: Raw prompt written to {log_filename}")
            except Exception as e:
                logger.error(f"Failed to write raw prompt: {e}")
            
            # Run LLM call in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.llm.extract, prompt, tool_schemas)
            content = result.get("content")
            tool_calls = result.get("tool_calls") or []
            
            # Append the LLM response to the same file
            try:
                with open(log_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n\n=== LLM RESPONSE ===\n")
                    f.write(f"Content Length: {len(content) if content else 0}\n")
                    f.write(f"Tool Calls Count: {len(tool_calls)}\n")
                    if content:
                        f.write(f"Content: {content}\n")
                    if tool_calls:
                        f.write("Tool Calls:\n")
                        for i, call in enumerate(tool_calls):
                            f.write(f"  {i+1}. {call.get('name')}: {call.get('arguments', {})}\n")
            except Exception as e:
                logger.error(f"Failed to log LLM response: {e}")
            
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
                if content and len(content) < 500 and not content.strip().startswith('{'):
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
                        flow_def = args.get('flow_definition', {})
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
                        if actual_tool_name == 'update_node' and 'node_id' in args:
                            node_id = args['node_id']
                            for node in flow.get('nodes', []):
                                if node.get('id') == node_id:
                                    logger.info(f"Agent iteration {iteration+1}: BEFORE TOOL - Node '{node_id}' current state: {node}")
                                    break
                        
                        # Provide defaults for optional parameters
                        if 'updates' in args and args['updates'] is None:
                            args['updates'] = {}
                            
                        logger.info(f"Agent iteration {iteration+1}: Final args being passed: {args}")
                        logger.info(f"Agent iteration {iteration+1}: flow_id={flow_id}, session={'present' if session else 'None'}")
                        
                        # Call with flow_definition as first parameter
                        tool_output = tool.func(flow, **args, flow_id=flow_id, session=session)
                        
                        logger.info(f"Agent iteration {iteration+1}: Tool '{actual_tool_name}' completed with output: {tool_output}")
                        
                        # ⚠️ Use structured tool responses instead of hacky string parsing!
                        # Import ToolResult for type checking
                        from app.agents.flow_modification_tools import ToolResult
                        
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
                                modification_details.append(f"{tool_output.action}: - Alterações aplicadas")
                            elif actual_tool_name in modification_tools:  # Legacy for non-ToolResult responses
                                flow_modified = True
                                node_id = args.get('node_id', '')
                                edge_info = f"{args.get('source', '')}->{args.get('target', '')}" if args.get('source') and args.get('target') else ''
                                modification_details.append(f"{actual_tool_name}: {node_id}{edge_info} - Alterações aplicadas")
                            
                            # Reload the flow from database to get the cumulative changes for next tool call
                            from app.db.repository import get_flow_by_id
                            updated_flow_db = get_flow_by_id(session, flow_id)
                            if updated_flow_db:
                                flow = updated_flow_db.definition  # Update flow for next tool call
                                logger.info(f"Agent iteration {iteration+1}: Reloaded flow from DB version {updated_flow_db.version}")
                                
                                # Verify the node was updated correctly
                                if actual_tool_name == 'update_node' and 'node_id' in args:
                                    node_id = args['node_id']
                                    for node in flow.get('nodes', []):
                                        if node.get('id') == node_id:
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
                    # Provide helpful error message with context
                    if "missing" in str(e) and "required" in str(e):
                        # Extract the missing parameter name and provide context
                        error_msg = str(e)
                        if "updates" in error_msg:
                            tool_output = f"Error: {actual_tool_name} requires an 'updates' parameter with the fields to modify. For example: updates={{'prompt': 'new text'}}, {error_msg}"
                        elif "flow_definition" in error_msg:
                            tool_output = f"Error: {actual_tool_name} requires a complete flow definition as JSON. {error_msg}"
                        else:
                            tool_output = f"Error: {actual_tool_name} is missing required arguments. {error_msg}. Check the tool schema and provide all required parameters."
                    else:
                        tool_output = f"Tool call failed: {actual_tool_name}. Error: {str(e)}"
                except Exception as e:
                    logger.error(f"Agent iteration {iteration+1}: Tool '{actual_tool_name}' unexpected error: {e}")
                    tool_output = f"Unexpected error calling {actual_tool_name}: {str(e)}"
                
                logger.info(f"Agent iteration {iteration+1}: Tool '{actual_tool_name}' returned: '{tool_output}'")
                # Add appropriate message based on success/failure using structured result
                if isinstance(tool_output, ToolResult):
                    if tool_output.success and tool_output.is_modification:
                        messages.append({"role": "assistant", "content": f"{tool_output.action} completed successfully. Flow has been updated."})
                    else:
                        messages.append({"role": "assistant", "content": f"Tool {tool_output.action} executed"})
                elif is_success and actual_tool_name in modification_tools:
                    # Legacy support for non-ToolResult responses
                    messages.append({"role": "assistant", "content": f"{actual_tool_name} completed successfully. Flow has been updated."})
                else:
                    # Generic message for read-only tools or errors  
                    messages.append({"role": "assistant", "content": f"Tool {actual_tool_name} executed"})
        
            # Check if we should complete after this iteration
            if should_complete:
                logger.info(f"Agent iteration {iteration+1}: Early completion triggered by validation after modifications")
                break
        
        # Create modification summary
        modification_summary = None
        if modification_details:
            modification_summary = "; ".join(modification_details)
        
        # Create a single human-friendly final message
        if flow_modified:
            final_message = "✅ Fluxo atualizado com sucesso! As seguintes alterações foram feitas:\n\n"
            for detail in modification_details:
                final_message += f"• {detail}\n"
            final_message += "\nO que você gostaria de ajustar agora?"
            outputs = [final_message]
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
            "  - Required: `id`, `kind: \"Question\"`, `key`, `prompt`",
            "  - Optional: `allowed_values`, `clarification`, `examples`, `dependencies`",
            "",
            "- **Decision**: Routes conversation based on logic",
            "  - Required: `id`, `kind: \"Decision\"`", 
            "  - Optional: `decision_type: \"llm_assisted\"`, `decision_prompt`",
            "",
            "- **Terminal**: Ends the conversation",
            "  - Required: `id`, `kind: \"Terminal\"`",
            "  - Optional: `reason`, `success: true/false`",
            "",
            "### Edges:",
            "Connect nodes with optional guards and priorities:",
            "- `source`: starting node id",
            "- `target`: destination node id", 
            "- `priority`: lower numbers evaluated first",
            "- `guard`: conditions like `{\"fn\": \"answers_has\", \"args\": {\"key\": \"field_name\"}}`",
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
            str(self._get_dentist_flow_example()),
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
            "- **CRITICAL: BATCH ALL TOOL CALLS** - If you identify multiple operations, do them ALL in ONE response!",
            "  - If you find 5 nodes to delete, call delete_node 5 times in the SAME response",
            "  - If you need to add 3 questions, call add_node 3 times in the SAME response", 
            "  - If you need to delete 2 nodes and add 1 edge, do ALL 3 calls in the SAME response",
            "  - **NEVER** do operations one at a time across multiple LLM calls unless truly complex reasoning is needed",
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
            "  - Example: After collecting \"service type\", route to dental vs orthodontics vs emergency workflows",
            "  - Example: After collecting \"urgency level\", route to urgent vs routine handling workflows", 
            "  - Decision nodes are invisible - they just branch the conversation to different question sets",
            "- **SIMPLE RULE**: Need info from user? → Question. Need to branch to different workflows? → Decision.",
            "- **Most flows don't need Decision nodes** - just Questions leading to more Questions!",
            "",
            "## CRITICAL: Removing Questions/Nodes:",
            "- **When user says \"remove a question\"** → YOU MUST DELETE THE NODE, not just edges!",
            "- **STEP 1**: Find the node by searching through ALL nodes in the flow definition", 
            "- **STEP 2**: Look at each node's `prompt` field to match user's description",
            "- **STEP 3**: Use `delete_node` with the correct `node_id` to remove the entire question",
            "- **STEP 4**: The `delete_node` tool will automatically handle connected edges",
            "- **WRONG**: Only calling `delete_edge` - this leaves the question in the flow!",
            "- **RIGHT**: Call `delete_node` to completely remove the question",
            "- **NEVER modify nodes the user didn't ask about**",
            "",
            "## Completion Instructions:",
            "- **FUNDAMENTAL RULE: ONE RESPONSE = ALL OPERATIONS** - If you identify 5 things to delete, make 5 delete_node calls in ONE response!",
            "- **COMPLETE ALL WORK IN ONE RESPONSE**: Make all necessary tool calls together, don't iterate one by one",
            "- **CRITICAL: DO THE WORK, DON'T JUST EXPLAIN IT**: If user asks for changes, USE TOOLS immediately!",
            "  - **WRONG**: \"I can remove that question for you...\" (just explaining)",
            "  - **RIGHT**: Call delete_node tool to actually remove it, THEN explain what you did",
            "- **WHEN TO STOP**: After making modifications, either:",
            "  1. Call `validate_flow` ONCE to check your work, OR", 
            "  2. Provide a final response with no tool calls if the work is clearly complete",
            "- **DO NOT** call validate_flow multiple times - one validation is enough",
            "- **DO NOT** call get_flow_summary unless user specifically asks for a summary",
            "- **STOP ITERATING**: Once you've completed the user's request, provide a final message and make no more tool calls",
            "",
            "### Tool Usage Examples:",
            "**EFFICIENT: Multiple operations in one response (ORDERED):**",
            "",
            "**Example: User asks \"Remove the payment question\" (single node):**",
            "1. Find the node with payment-related `prompt` text",
            "2. Call `delete_node` with that node's ID - this removes the question AND its edges",
            "3. Done! (delete_node handles everything automatically)",
            "",
            "**Example: User asks \"Remove covered/uncovered questions\" (multiple nodes):**",
            "1. Find ALL nodes related to coverage (questions, decisions, etc.)",
            "2. Call `delete_node` for node1, `delete_node` for node2, `delete_node` for node3 - ALL in the SAME response!",
            "3. Done! Don't wait between deletions - batch them all together!",
            "",
            "**Example: User asks \"Remove payment question and connect address to phone\":**",  
            "1. Call `delete_node` to remove payment question (handles its edges automatically)",
            "2. Call `add_edge` to create new connection from address to phone",
            "- All in the SAME response, in the CORRECT ORDER, not separate iterations!",
            "",
            "**Adding a question:**",
            '```',
            'add_node:',
            '  node_definition:',
            '    id: "q.new_question"',
            '    kind: "Question"', 
            '    key: "new_question"',
            '    prompt: "What is your question?"',
            '```',
            "",
            "**Adding a decision (for routing logic only):**",
            '```', 
            'add_node:',
            '  node_definition:',
            '    id: "d.service_routing"',
            '    kind: "Decision"',
            '    label: "Route by service type"',
            '    decision_type: "llm_assisted"',
            '    decision_prompt: "Route different service types to their appropriate question sets"',
            '```',
            "",
            "**Adding an edge:**",
            '```',
            'add_edge:',
            '  source: "q.source_node"',
            '  target: "q.target_node"',  
            '  priority: 0',
            '  condition_description: "Description of when this path is taken"',
            '```',
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
            f"## Current Flow:",
            f"```json",
            f"{json.dumps(flow, indent=2) if flow else 'null'}",
            f"```",
            "",
        ])
        
        # Add frontend context if simplified view is enabled
        if simplified_view_enabled and active_path:
            lines.extend([
                f"## 🎯 IMPORTANT: Frontend View Context",
                f"- **Simplified view is ENABLED** - User can only see one conversation path",
                f"- **Active path selected**: '{active_path}'",
                f"- **Focus ONLY on nodes related to '{active_path}' path**",
                f"- **Do NOT modify other paths** - user can't see them and didn't ask about them",
                f"- **When user asks to 'remove/add/modify', they mean within the '{active_path}' context**",
                "",
            ])
        elif simplified_view_enabled:
            lines.extend([
                f"## 🎯 IMPORTANT: Frontend View Context", 
                f"- **Simplified view is ENABLED** but no specific path selected",
                f"- **Ask user to specify which path they're referring to** if their request is ambiguous",
                "",
            ])
        
        # Conversation history
        if history:
            lines.append("## Conversation History:")
            for m in history:
                lines.append(f"{m['role'].title()}: {m['content']}")
            lines.append("")
        
        lines.append("How can I help you modify or create your flow?")
        
        return "\n".join(lines)
    
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
