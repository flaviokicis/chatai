from __future__ import annotations

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

    def process(
        self, 
        flow: dict[str, Any], 
        history: Sequence[dict[str, str]], 
        flow_id: UUID | None = None, 
        session: Session | None = None
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
        for iteration in range(10):  # hard limit to avoid infinite loops
            logger.info(f"Agent iteration {iteration+1}: Building prompt...")
            prompt = self._build_prompt(flow, messages)
            logger.info(f"Agent iteration {iteration+1}: Calling LLM extract with prompt length {len(prompt)}")
            
            result = self.llm.extract(prompt, tool_schemas)
            content = result.get("content")
            tool_calls = result.get("tool_calls") or []
            
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
                    if actual_tool_name == "set_entire_flow":
                        # set_entire_flow: flow_definition is provided by LLM
                        flow_def = args.get('flow_definition', {})
                        user_msg = args.get('user_message')
                        logger.info(f"Agent iteration {iteration+1}: Calling set_entire_flow with {len(flow_def.get('nodes', []))} nodes")
                        tool_output = tool.func(flow_def, user_message=user_msg, flow_id=flow_id, session=session)
                        # Update local flow if successful
                        if "✅" in tool_output or (user_msg and user_msg in tool_output):
                            flow = flow_def
                            flow_modified = True
                            modification_details.append(f"set_entire_flow: {user_msg or 'Updated complete flow definition'}")
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
                        
                        # Extract user_message if present
                        user_msg = args.pop('user_message', None)
                        logger.info(f"Agent iteration {iteration+1}: Extracted user_message: {user_msg}")
                        
                        # Provide defaults for optional parameters
                        if 'updates' in args and args['updates'] is None:
                            args['updates'] = {}
                            
                        logger.info(f"Agent iteration {iteration+1}: Final args being passed: {args}")
                        logger.info(f"Agent iteration {iteration+1}: flow_id={flow_id}, session={'present' if session else 'None'}")
                        
                        # Call with flow_definition as first parameter
                        tool_output = tool.func(flow, **args, user_message=user_msg, flow_id=flow_id, session=session)
                        
                        logger.info(f"Agent iteration {iteration+1}: Tool '{actual_tool_name}' completed with output: {tool_output}")
                        
                        # ⚠️ CRITICAL BUG FIX: Each tool call must work with the latest flow state from database!
                        # The tools persist changes to DB, but the next tool needs to work with those changes.
                        if "✅" in tool_output or (user_msg and user_msg in tool_output):
                            logger.info(f"Agent iteration {iteration+1}: Tool reported success, reloading flow from database for next tool")
                            
                            # Track successful flow modification
                            flow_modified = True
                            node_id = args.get('node_id', '')
                            edge_info = f"{args.get('source', '')}->{args.get('target', '')}" if args.get('source') and args.get('target') else ''
                            modification_details.append(f"{actual_tool_name}: {node_id}{edge_info} - {user_msg or 'Applied changes'}")
                            
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
                outputs.append(tool_output)
                messages.append({"role": "assistant", "content": tool_output})
        
        # Create modification summary
        modification_summary = None
        if modification_details:
            modification_summary = "; ".join(modification_details)
        
        logger.info(f"FlowChatAgent.process complete: returning {len(outputs)} outputs, flow_modified={flow_modified}")
        if flow_modified:
            logger.info(f"Flow modifications: {modification_summary}")
        
        return FlowChatResponse(
            messages=outputs,
            flow_was_modified=flow_modified,
            modification_summary=modification_summary
        )

    def _build_prompt(self, flow: dict[str, Any], history: Sequence[dict[str, str]]) -> str:
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
            "- For flow modifications: Call `set_entire_flow` tool with the complete modified flow",
            "- For node updates: Call `update_node` with node_id AND updates={field: value}",
            "- For edge updates: Call `update_edge` with source, target, AND updates={field: value}",
            "- For validation: Call `validate_flow` tool", 
            "- For summaries: Call `get_flow_summary` tool",
            "- **TOOL REQUIREMENTS: Always provide ALL required parameters**",
            "  - update_node: requires node_id AND updates (dict)",
            "  - update_edge: requires source, target AND updates (dict)",  
            "  - set_entire_flow: requires complete flow_definition (dict)",
            "- **IMPORTANT: Always provide 'user_message' parameter** with a friendly message in the user's language",
            "  - Example (Portuguese): user_message: \"Escala de dor alterada de 1-10 para 1-5 com sucesso!\"",
            "  - Example (English): user_message: \"Pain scale successfully updated from 1-10 to 1-5!\"",
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
