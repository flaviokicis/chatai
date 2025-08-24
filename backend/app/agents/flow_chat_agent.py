from __future__ import annotations

import json
from typing import Any, Callable, Sequence

from pydantic import BaseModel

from app.core.llm import LLMClient


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

    def process(self, flow: dict[str, Any], history: Sequence[dict[str, str]]) -> list[str]:
        """Process conversation and return assistant responses."""

        messages = list(history)
        outputs: list[str] = []
        tool_schemas = [t.args_schema for t in self.tools.values() if t.args_schema]
        # Simple loop allowing multiple tool invocations
        for _ in range(10):  # hard limit to avoid infinite loops
            prompt = self._build_prompt(flow, messages)
            result = self.llm.extract(prompt, tool_schemas)
            content = result.get("content")
            if content:
                outputs.append(content)
                messages.append({"role": "assistant", "content": content})
            tool_calls = result.get("tool_calls") or []
            if not tool_calls:
                break
            for call in tool_calls:
                name = call.get("name")
                args = call.get("arguments", {})
                tool = self.tools.get(name)
                if not tool:
                    continue
                tool_output = tool.func(**args)
                outputs.append(tool_output)
                messages.append({"role": "assistant", "content": tool_output})
        return outputs

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
            "- Always provide complete, valid JSON flow definitions",
            "- Use meaningful IDs: `q.field_name` for questions, `d.description` for decisions, `t.outcome` for terminals",
            "- Include `condition_description` on edges to explain routing logic",
            "- Set up proper priorities on edges (lower numbers = higher priority)",
            "- Add `decision_prompt` to decision nodes for LLM-assisted routing",
            "- Use `allowed_values` for constrained choices",
            "- Include helpful metadata like flow name, description, and UI labels",
            "",
            "## When User Provides WhatsApp Conversation:",
            "1. Analyze the conversation flow and identify main paths/scenarios",
            "2. Extract key questions that need to be asked",
            "3. Identify decision points where conversation branches",
            "4. Create appropriate subgraphs for different scenarios",
            "5. Set up global questions that apply to all paths",
            "6. Provide complete flow JSON ready for immediate use",
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
    
    def _get_dentist_flow_example(self) -> dict[str, Any]:
        """Return the dentist flow example for prompt context."""
        return {
            "schema_version": "v2",
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
