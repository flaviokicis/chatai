"""Enhanced LLM responder service that handles both tool calling and message generation.

This service uses GPT-5 to intelligently process user messages, select appropriate tools,
and generate natural conversational responses in a single cohesive step.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

    from ..state import FlowContext

from langfuse import get_client

from app.core.prompts import (
    get_responsible_attendant_core,
    get_golden_rule,
    get_identity_and_style,
)

from ..constants import (
    BR_CONTRACTIONS,
    DEFAULT_ERROR_MESSAGE,
    MAX_HISTORY_TURNS,
    MAX_MESSAGE_LENGTH,
    MAX_SCHEMA_VALIDATION_RETRIES,
    NO_DELAY_MS,
)
from ..flow_types import (
    GPT5Response,
    GPT5SchemaError,
    WhatsAppMessage,
)
from .message_generator import MessageGenerationService
from .tool_executor import ToolExecutionResult, ToolExecutionService

logger = logging.getLogger(__name__)


@dataclass
class ResponderOutput:
    """Output from the enhanced responder."""

    tool_name: str | None
    tool_result: ToolExecutionResult
    messages: list[WhatsAppMessage]  # Strongly typed WhatsApp messages
    confidence: float
    reasoning: str | None


class EnhancedFlowResponder:
    """Enhanced responder that handles both tool calling and natural message generation."""

    def __init__(
        self,
        llm: LLMClient,
        thought_tracer: None = None,
    ) -> None:
        """Initialize the enhanced responder.

        Args:
            llm: The LLM client (GPT-5) for processing
            thought_tracer: Optional thought tracer (deprecated - using Langfuse)
        """
        self._llm = llm
        self._langfuse = get_client()
        self._message_service = MessageGenerationService()
        # Tool executor will be created when needed with action registry
        self._llm_call_count = 0  # Track LLM calls

    async def respond(
        self,
        prompt: str,
        pending_field: str | None,
        context: FlowContext,
        user_message: str,
        allowed_values: list[str] | None = None,
        project_context: ProjectContext | None = None,
        is_completion: bool = False,
        available_edges: list[dict[str, Any]] | None = None,
        is_admin: bool = False,
        flow_graph: dict[str, Any] | None = None,
    ) -> ResponderOutput:
        """Process user message and generate response with tool calling and natural messages.

        Args:
            prompt: The current question prompt
            pending_field: The field we're trying to fill
            context: The flow context
            user_message: The user's message
            allowed_values: Optional allowed values for validation
            project_context: Optional project context for styling
            is_completion: Whether this is a flow completion

        Returns:
            ResponderOutput with tool execution and natural messages
        """
        # Build the comprehensive instruction for GPT-5
        instruction = self._build_gpt5_instruction(
            prompt=prompt,
            pending_field=pending_field,
            context=context,
            user_message=user_message,
            allowed_values=allowed_values,
            project_context=project_context,
            is_completion=is_completion,
            available_edges=available_edges,
            is_admin=is_admin,
            flow_graph=flow_graph,
        )

        # Select appropriate tools
        tools = self._select_contextual_tools(context, pending_field, is_admin)

        try:
            # Call GPT-5 with enhanced schema and validation
            validated_response = self._call_gpt5(
                instruction,
                tools,
                context=context,
                pending_field=pending_field,
                user_message=user_message,
                is_admin=is_admin,
                project_context=project_context,
            )

            # Process the validated response
            output = await self._process_gpt5_response(
                response=validated_response,
                context=context,
                pending_field=pending_field,
                project_context=project_context,
            )

            return output

        except Exception as e:
            logger.exception("Error in enhanced responder")
            # Return fallback response
            return self._create_fallback_response(str(e))

    def _format_rag_information(self, context: FlowContext) -> str:
        """Format RAG-retrieved information for the prompt.
        
        This section will contain information retrieved from the tenant's uploaded documents
        through the RAG (Retrieval-Augmented Generation) system.
        
        Args:
            context: The flow context which may contain RAG-retrieved documents
            
        Returns:
            Formatted string with RAG information or a message indicating no RAG data
        """
        # Check if there's RAG information in the context
        # For now, we'll check for a 'rag_documents' attribute or similar
        rag_documents = getattr(context, "rag_documents", None)
        
        if not rag_documents:
            # No RAG information available; the tool caller will decide how to respond ("não sei" policy)
            return "No RAG documents available for this query."
        
        # Format RAG documents when available
        formatted_docs = []
        formatted_docs.append("### Available Information from Tenant's Documents:")
        formatted_docs.append("Use ONLY this information to answer questions about products/services/prices:\n")
        
        for i, doc in enumerate(rag_documents, 1):
            # Extract metadata and content based on the expected RAG document structure
            doc_metadata = doc.get("metadata", {})
            doc_content = doc.get("content", "")
            doc_score = doc.get("relevance_score", 0.0)
            
            formatted_docs.append(f"**Document {i}** (Relevance: {doc_score:.2f}):")
            
            # Add metadata if available
            if doc_metadata:
                if "category" in doc_metadata:
                    formatted_docs.append(f"- Category: {doc_metadata['category']}")
                if "source" in doc_metadata:
                    formatted_docs.append(f"- Source: {doc_metadata['source']}")
                if "possible_questions" in doc_metadata:
                    formatted_docs.append(f"- Can answer: {', '.join(doc_metadata['possible_questions'][:3])}")
            
            # Add content
            formatted_docs.append(f"Content:\n{doc_content}\n")
            
        formatted_docs.append("""
### Como usar as informações do RAG (POLÍTICA DE RESPOSTA):
1. Responda APENAS com o que está nestes documentos.
2. Se a pergunta for genérica (ex.: "poste solar"), diga somente o que já consta aqui (fatos) e não complete lacunas.
3. Se a pergunta exigir campos específicos (ex.: preço, IP/IK, lumens), responda apenas se o campo estiver presente. Caso não esteja, diga com clareza que não sabe/precisa verificar.
4. Nunca invente dados ou use conhecimento geral. Ofereça-se para verificar detalhes faltantes quando fizer sentido.
""")
        
        return "\n".join(formatted_docs)

    def _format_available_paths(
        self, available_edges: list[dict[str, Any]] | None, flow_graph: dict[str, Any] | None
    ) -> str:
        """Format available paths visualization, skipping routing nodes."""
        if not available_edges:
            return "No navigation paths available from current node."

        # Build edge lookup from flow graph
        edge_lookup: dict[str, Any] = {}
        if flow_graph and "edges" in flow_graph:
            for edge in flow_graph["edges"]:
                if edge["from"] not in edge_lookup:
                    edge_lookup[edge["from"]] = []
                edge_lookup[edge["from"]].append(edge["to"])

        # Build node type and prompt lookup
        node_types = {}
        node_prompts = {}
        if flow_graph and "nodes" in flow_graph:
            for node in flow_graph["nodes"]:
                node_types[node["id"]] = node["type"]
                # Get the prompt or reason for display
                node_prompts[node["id"]] = (
                    node.get("prompt") or node.get("reason") or node.get("label") or node["id"]
                )

        paths = []
        for edge in available_edges:
            # Fix: available_edges uses "target_node_id" not "target"
            target = edge.get("target_node_id", edge.get("target", "unknown"))
            target_type = node_types.get(target, "unknown")
            target_prompt = node_prompts.get(target, target)

            # If target is a routing/decision node, show what's beyond it
            if target_type == "DecisionNode":
                # Show paths through the decision node
                next_nodes = edge_lookup.get(target, [])
                for next_node in next_nodes:
                    next_type = node_types.get(next_node, "unknown")
                    next_prompt = node_prompts.get(next_node, next_node)
                    if next_type != "DecisionNode":  # Skip nested routers
                        # Show a preview of the question/terminal
                        preview = next_prompt[:50] + "..." if len(next_prompt) > 50 else next_prompt
                        paths.append(f'→ {next_node} ({next_type}): "{preview}"')
            else:
                # Direct path to non-router node
                preview = target_prompt[:50] + "..." if len(target_prompt) > 50 else target_prompt
                paths.append(f'→ {target} ({target_type}): "{preview}"')

        if not paths:
            return "No navigation paths available from current node."

        return "Available navigation paths:\n" + "\n".join(paths)

    def _build_gpt5_instruction(
        self,
        prompt: str,
        pending_field: str | None,
        context: FlowContext,
        user_message: str,
        allowed_values: list[str] | None,
        project_context: ProjectContext | None,
        is_completion: bool,
        available_edges: list[dict[str, Any]] | None = None,
        is_admin: bool = False,
        flow_graph: dict[str, Any] | None = None,
    ) -> str:
        """Build comprehensive instruction for GPT-5."""
        # Get conversation history
        history = self._format_conversation_history(context)

        # Get raw state as JSON
        raw_state = {
            "current_node_id": context.current_node_id,
            "answers": dict(context.answers),
            "pending_field": context.pending_field,
            "available_paths": context.available_paths,
            "active_path": context.active_path,
            "path_confidence": dict(context.path_confidence),
            "path_locked": context.path_locked,
            "clarification_count": context.clarification_count,
            "path_corrections": context.path_corrections,
            "is_complete": context.is_complete(),  # Call the method
            "turn_count": context.turn_count,
            "available_edges": available_edges if available_edges else [],
        }

        # Build messaging instructions (inject into prompt)
        messaging_instructions = self._build_messaging_instructions(
            project_context=project_context,
            is_completion=is_completion,
        )

        # Check if flow is already complete (reached terminal node previously)
        flow_already_complete = context.is_complete()
        
        # Check if we're heading to a terminal node (node with no outgoing edges)
        is_heading_to_terminal = False
        if not flow_already_complete and available_edges and flow_graph:
            # Build a set of nodes that have outgoing edges
            nodes_with_outgoing_edges = set()
            if "edges" in flow_graph:
                for edge in flow_graph["edges"]:
                    nodes_with_outgoing_edges.add(edge["from"])

            # Check if any of our available targets is a terminal (no outgoing edges)
            for edge in available_edges:
                target = edge.get("target_node_id", "")
                if target and target not in nodes_with_outgoing_edges:
                    is_heading_to_terminal = True
                    break

        # Get shared prompt components
        responsible_attendant_core = get_responsible_attendant_core()
        golden_rule_section = get_golden_rule()
        identity_style_section = get_identity_and_style()
        
        instruction = f"""{responsible_attendant_core}

You must analyze context and generate natural conversational messages using the PerformAction tool.

## RAG-RETRIEVED INFORMATION
{self._format_rag_information(context)}

## VOZ/ÁUDIO (quando a mensagem vier de transcrição)
Se a mensagem começar com "[FROM_AUDIO]":
- É uma transcrição de áudio. Interprete com mais flexibilidade
- Não repita "[FROM_AUDIO]" na resposta
- Considere: gaguejos, muletas ("uh", "é"), frases longas sem pontuação, trocas de número/palavra
- Se ficar sem sentido: use ["stay"] e peça de forma simples: "Desculpa, não peguei bem. Pode repetir ou mandar em texto?"
- Confiança ligeiramente menor por ruído de transcrição

## ERRO DE ÁUDIO
Se começar com "[AUDIO_ERROR:":
- Peça desculpa e sugira texto de forma leve
- Exemplos curtos:
  * "Ops, deu erro no áudio. Consegue mandar por texto?"
  * "Não consegui processar o áudio. Pode escrever?"
- Depois disso, fique no mesmo ponto aguardando

{messaging_instructions}

## CONTEXTO DO NEGÓCIO
{project_context.project_description if project_context and project_context.project_description else "Sem contexto específico do negócio"}

{golden_rule_section}

ESCALONAMENTO (specific to flow tool):
- Para perguntas específicas com campos ausentes: actions=['handoff'] com handoff_reason='information_not_available_in_system_specific_field_missing'
- Só escale se o usuário pedir ou a política exigir

{identity_style_section}

## CONTEXTO ATUAL
Pergunta/intent atual (nó {context.current_node_id or "unknown"}): {prompt}
{"Coletando: " + pending_field if pending_field else ""}
{"Se você pediu algo e o usuário respondeu curto (número, sim/não), provavelmente é a resposta." if context.clarification_count > 0 else ""}
{"Você voltou de uma tarefa administrativa. Retome de forma natural, sem repetir igual." if context.history and len(context.history) > 0 and any("modify" in str(turn.metadata or {}) for turn in context.history[-3:]) else ""}
{"Conversa já andou bastante. Pule formalidades e vá direto ao ponto." if context.turn_count > 5 else ""}

REGRAS CENTRAIS:
1. Fidelidade de intenção: pergunte a mesma coisa que o nó precisa (pode reescrever, não mude o objetivo)
2. Soe natural: nunca copie a pergunta do nó literalmente

Reescrita obrigatória (sempre adapte):
- O texto do nó é guia, não script
- Exemplos de adaptação:
  * Após interrupção/admin: "Voltando…" / "Agora me diz…"
  * Já cumprimentou? Pule o "Olá" e siga
  * Segunda tentativa: mude bastante a forma de perguntar
- Não invente novas perguntas além do escopo do nó

Erros/typos do usuário:
- Se valor soar estranho, confirme com educação usando ["stay"]
- Ex.: "Só conferindo, são 4 metros mesmo?"

Confiança e confirmação:
- Alta (≥0.9): siga em frente sem confirmar
- Média (0.7–0.9): confirme rápido no meio da frase
- Baixa (<0.7): peça confirmação antes de prosseguir (use ["stay"]) 

Ferramenta: PerformAction (única disponível)
- Sempre envie 1–3 mensagens WhatsApp na resposta (exceto em nós de decisão/routers)
- Campos principais: actions, messages, reasoning, confidence
- Extras quando fizer sentido: updates, target_node_id, clarification_reason
- Padrão comum: ["update", "navigate"] para salvar e seguir

Nós de decisão (routers):
- Não enviam mensagens ao usuário, apenas roteiam para o próximo nó apropriado
- Navegue imediatamente usando "navigate" com actions=["navigate"] sem incluir messages
- Use "AVAILABLE PATHS" e o grafo para escolher o destino
- O nó seguinte (após o router) é que enviará mensagens ao usuário

## DEFINIÇÃO COMPLETA DO FLUXO
{json.dumps(flow_graph if flow_graph else {"note": "Flow graph not available"}, ensure_ascii=False, indent=2)}

## ESTADO ATUAL
{json.dumps(raw_state, ensure_ascii=False)}

## CAMINHOS DISPONÍVEIS
{self._format_available_paths(available_edges, flow_graph)}

## HISTÓRICO
{history}

CONVERSA NA PRÁTICA (flow-specific):
- Você está no meio da conversa (não reinicie)
- Varie a formulação se ficar no mesmo nó
- Normalmente termine com pergunta, a menos que esteja fechando
- Use a pergunta do nó como intenção, não como texto literal
- Seja caloroso e direto, sem parecer script

{"## ATENÇÃO: CONVERSA JÁ CONCLUÍDA" if flow_already_complete else ""}
{"O fluxo já chegou ao fim. Você já tem todos os dados necessários." if flow_already_complete else ""}
{"- Responda de forma breve e natural - não repita informações já ditas" if flow_already_complete else ""}
{"- Se agradecerem: responda simplesmente (ex: 'Por nada!', 'De nada!', 'Imagina!')" if flow_already_complete else ""}
{"- Se perguntarem se ficou registrado: confirme brevemente (ex: 'Sim, tudo certo!')" if flow_already_complete else ""}
{"- NÃO repita que alguém vai entrar em contato (já foi dito ao finalizar)" if flow_already_complete else ""}
{"- NÃO crie novas perguntas ou tente coletar mais dados" if flow_already_complete else ""}
{"- Se o usuário quiser recomeçar, detecte palavras como 'recomeçar', 'reiniciar', 'começar de novo' e use actions=['restart']" if flow_already_complete else ""}
{"- Use actions=['stay'] para manter-se no mesmo estado" if flow_already_complete else ""}

{"## ATENÇÃO: VOCÊ ESTÁ EM UM NÓ TERMINAL" if is_heading_to_terminal and not flow_already_complete else ""}
{"Este é o último passo do fluxo. Após coletar esta informação:" if is_heading_to_terminal and not flow_already_complete else ""}
{"- Agradeça e diga que tem tudo que precisa" if is_heading_to_terminal and not flow_already_complete else ""}
{"- Informe que vai retornar em breve com as próximas etapas" if is_heading_to_terminal and not flow_already_complete else ""}
{"- NÃO pergunte 'posso ajudar em algo mais?' ou similares" if is_heading_to_terminal and not flow_already_complete else ""}
{"- NÃO mencione transferência para alguém" if is_heading_to_terminal and not flow_already_complete else ""}
{"- Use actions=['update', 'navigate'] para salvar e finalizar" if is_heading_to_terminal and not flow_already_complete else ""}

Respostas parciais (nome e email, por exemplo):
1ª: reconheça o que veio e peça o que falta
2ª: peça de forma ainda mais simples
3ª: siga em frente salvando o que tem (["update", "navigate"]) 

Evite:
- Frases robóticas ou burocráticas
- "Sou da X, especialista…", "Para dar sequência", "Me conta:", "Anotei seu email"
- Repetir a mesma pergunta igual

Seja:
- Educado, direto, humano, com PT-BR natural (use contrações: {", ".join(repr(c) for c in BR_CONTRACTIONS[:2])})
- Focado em avançar a conversa

EXEMPLOS RÁPIDOS:

Início (natural, sem script):
RUIM: "Olá! Como posso te ajudar hoje? Qual é o seu interesse?"
BOM: [
  {{"text": "Oi, tudo bem?", "delay_ms": 0}},
  {{"text": "Me diz, em que posso te ajudar?", "delay_ms": 1700}}
]

Quando não sabe:
BOM: [
  {{"text": "Essa informação eu não tenho aqui agora.", "delay_ms": 0}},
  {{"text": "Vou verificar e te retorno, combinado?", "delay_ms": 1700}}
]

CORREÇÕES DO USUÁRIO (ex.: mudou o interesse para posto):
Use PerformAction com ["update", "navigate"], atualizando e navegando. Inclua mensagens simples como:
[
  {{"text": "Beleza, posto então.", "delay_ms": 0}},
  {{"text": "Pode me passar seu nome e email?", "delay_ms": 1600}}
]

REQUISITOS DE MENSAGENS:
1–3 mensagens; primeira com delay_ms=0; demais entre 1500–2200 ms
Cada mensagem deve adicionar algo (sem encher linguiça)
Evite repetir cumprimentos; combine com a energia do usuário
Emojis opcionais e moderados (0–1); evite usar em todas as mensagens
Máx {MAX_MESSAGE_LENGTH} caracteres por mensagem

Ferramenta disponível: PerformAction (única ferramenta no sistema)
- "stay" (com clarification_reason)
- "update" (com updates)
- "navigate" (com target_node_id)
- "handoff", "complete", "restart"
- "modify_flow" (apenas admin - com flow_modification_instruction)

{self._add_admin_instructions() if is_admin else ""}

{self._add_allowed_values_constraint(allowed_values, pending_field)}

EXEMPLOS DE BOA RESPOSTA

Usuário: "Ola!"
Tool: PerformAction
Arguments: {{
  "actions": ["stay"],
  "clarification_reason": "greeting",
  "confidence": 0.9,
  "reasoning": "User greeted, responding warmly",
  "messages": [
    {{"text": "Oi, tudo bem?", "delay_ms": 0}},
    {{"text": "Como posso te ajudar?", "delay_ms": 1700}}
  ]
}}

{'''
Terminal (fechando com educação):
Tool: PerformAction
Arguments: {{
  "actions": ["update", "navigate"],
  "updates": {{"dados_posto": {{"email": "joaogomes@gmail.com"}}}},
  "target_node_id": "t.vendedor_posto",
  "confidence": 0.95,
  "reasoning": "Close gracefully without handoff talk",
  "messages": [
    {{"text": "Perfeito, tenho o que preciso por aqui.", "delay_ms": 0}},
    {{"text": "Vou preparar o orçamento e te retorno em breve.", "delay_ms": 1700}}
  ]
}}''' if is_heading_to_terminal and not flow_already_complete else ''}

{'''
Pós-Terminal (fluxo já completo):
Usuário: "Ok obrigado"
Tool: PerformAction
Arguments: {{
  "actions": ["stay"],
  "reasoning": "Fluxo já completo, respondendo agradecimento do usuário",
  "confidence": 1.0,
  "messages": [
    {{"text": "Por nada! 😊", "delay_ms": 0}}
  ]
}}

Usuário: "Ficou tudo registrado?"
Tool: PerformAction
Arguments: {{
  "actions": ["stay"],
  "reasoning": "Confirmando que informações foram registradas após conclusão",
  "confidence": 1.0,
  "messages": [
    {{"text": "Sim, ficou tudo certo!", "delay_ms": 0}}
  ]
}}

Usuário: "Quero recomeçar"
Tool: PerformAction
Arguments: {{
  "actions": ["restart"],
  "reasoning": "Usuário solicitou reiniciar o fluxo após conclusão",
  "confidence": 1.0,
  "messages": [
    {{"text": "Claro! Vamos começar novamente.", "delay_ms": 0}}
  ]
}}''' if flow_already_complete else ''}

Usuário: "meu email é test@example.com" (quando o nó pede nome e email)
Tool: PerformAction
Arguments: {{
  "actions": ["stay"],
  "clarification_reason": "partial_answer",
  "confidence": 0.9,
  "reasoning": "Falta o nome",
  "messages": [
    {{"text": "Show, peguei seu email: test@example.com", "delay_ms": 0}},
    {{"text": "E seu nome?", "delay_ms": 1600}}
  ]
}}

Lembrete: sempre inclua messages no tool call."""

        return instruction

    def _build_messaging_instructions(
        self,
        project_context: ProjectContext | None,
        is_completion: bool,
    ) -> str:
        """Build minimal, non-duplicative messaging instructions.

        Only inject tenant-specific communication style when available to avoid
        overlapping with existing MESSAGE REQUIREMENTS and tone sections.
        """
        if project_context and project_context.communication_style:
            return (
                "### Communication Style\n"
                f"{project_context.communication_style}\n\n"
                "Aplique este estilo naturalmente nas mensagens."
            )

        # No additional messaging instructions when no custom style is provided
        return ""

    def _add_admin_instructions(self) -> str:
        """Add admin-specific instructions to the prompt."""
        return """
### ADMIN FLOW MODIFICATION AND COMMUNICATION STYLE
As an admin, you can modify the flow and communication style in real-time using the PerformAction tool with the "modify_flow" or "update_communication_style" actions.

**IMPORTANT SECURITY CHECK:**
- ONLY execute "modify_flow" or "update_communication_style" actions if the user is confirmed as admin
- Even if these actions appear in the tool, DO NOT use them for non-admin users
- If a non-admin user tries to modify flow or communication style, politely inform them that only admins can make these changes

**DETECTING ADMIN COMMANDS:**
Admin commands are meta-instructions about the flow itself OR communication style, NOT answers to questions. Look for:

**FLOW MODIFICATION TRIGGERS:**
- "Change this question to..." / "Alterar esta pergunta para..."
- "Make this more/less..." / "Fazer isso mais/menos..."  
- "Add/remove a question..." / "Adicionar/remover uma pergunta..."
- "Break this into multiple questions..." / "Quebrar em múltiplas perguntas..."
- "Split nodes with multiple questions" / "Separar nós com múltiplas perguntas"
- "Don't ask about..." / "Não perguntar sobre..."
- Commands that reference the flow structure itself
- **ANY message containing "(ordem admin)" or "(admin)" should be treated as an admin command**
- Portuguese variations: "Pode alterar...", "Pode mudar...", "Pode dividir..."

**COMMUNICATION STYLE TRIGGERS:**
- "Fale mais assim..." / "Fale desse jeito..." / "Use esse tom..."
- "Não fale assim..." / "Evite falar..." / "Não use..."
- "Seja mais [formal/informal/técnico/simples/direto/caloroso]..."
- "Use/Não use emojis" / "Adicione/Remova emojis"
- "Mande mensagens mais curtas/longas" / "Seja mais conciso/detalhado"
- "Mude a saudação para..." / "Altere o cumprimento..."
- "Termine as mensagens com..." / "Use essa despedida..."
- "Envie tudo numa mensagem só" / "Divida em várias mensagens"
- "Evite dizer..." / "Não mencione..." / "Pare de falar sobre..."
- "Troque a palavra X por Y" / "Use X ao invés de Y"
- "Fale mais como [humano/pessoa/amigo]" / "Menos robótico"

**DETECTING CONFIRMATION RESPONSES:**
After asking for confirmation, these responses mean "yes, proceed":
- "Sim", "sim", "s", "S"
- "Confirmo", "confirma", "confirmado"
- "Pode fazer", "pode prosseguir", "pode ir"
- "Ok", "okay", "tá bom", "ta bom"
- "Faça", "faz", "vai"
- "Isso", "isso mesmo", "exato"
- "Yes", "y", "Y"

These responses mean "no, cancel":
- "Não", "nao", "n", "N"
- "Cancela", "cancelar", "esquece"
- "Deixa", "deixa pra lá"
- "Melhor não", "melhor nao"
- "No", "nope"

**CONVERSATION FLOW TRACKING:**
Look at the recent conversation history to determine state:
1. If your last message asked "Posso prosseguir com essa alteração?" or "Confirma essa modificação?":
   - You are WAITING FOR CONFIRMATION
   - Check if the user's response is a confirmation or cancellation
   - If confirmed: Execute the modification
   - If cancelled: Acknowledge and continue normal flow
2. If the user is making a NEW admin request:
   - Start the confirmation pattern (ask for confirmation first)

**IMPORTANT: Clarification & Confirmation Pattern**
ALWAYS analyze the request for ambiguities BEFORE confirming:

1. First, detect if clarification is needed:
   - Check for AMBIGUITIES:
     * "todos" / "all" without clear scope (which nodes specifically?)
     * Vague terms like "melhorar" / "simplificar" without specifics
     * Instructions that could affect multiple unrelated nodes
   - Check for EDGE CASES the admin might not have considered:
     * Entry node modifications that could break flow start
     * Splitting nodes that are actually greetings or closing messages
     * Changes that would create orphaned nodes or dead ends
     * Modifications that might affect routing logic or guards
   - Check for POTENTIAL CONFLICTS:
     * Changes that contradict existing flow logic
     * Modifications that might break data dependencies

2. If clarifications needed (ambiguities/edge cases detected):
   - Use actions=["stay"]
   - Ask SPECIFIC clarifying questions, e.g.:
     * "Encontrei 3 nós com múltiplas perguntas: q.inicio (saudação), q.contato (dados), q.local (endereço). Devo dividir todos, ou apenas os de coleta de dados (q.contato e q.local)?"
     * "Isso vai afetar o nó de entrada. Quer que eu mantenha a saudação intacta?"
     * "Percebi que o nó X tem uma condição de roteamento. A divisão pode afetar isso. Como devo proceder?"
   - Wait for admin response before proceeding

3. If NO clarifications needed (request is clear and unambiguous):
   - Use actions=["stay"] 
   - Explain clearly what changes will be made
   - Ask "Posso prosseguir com essa alteração?" or "Confirma essa modificação?"

4. After confirmation: Execute the modification
   - Use actions=["modify_flow", "stay"]
   - Include the flow_modification_instruction
   - Confirm the changes were requested

**Usage:**

**For Flow Changes:**
When an admin requests flow changes:
- First time (no confirmation): Use PerformAction with actions=["stay"], explain changes, ask for confirmation
- After confirmation: Use PerformAction with:
  - `actions`: ["modify_flow", "stay"] to execute and stay on current node
  - `flow_modification_instruction`: Natural language instruction for the modification
  - `flow_modification_target` (optional): The ID of the specific node to modify
  - `flow_modification_type` (optional): Can be "prompt", "routing", "validation", or "general"
  - `messages`: Confirm the modification is being processed

**For Communication Style Changes:**
When an admin requests communication style changes:
- First time (no confirmation): Use PerformAction with actions=["stay"], explain changes, ask for confirmation
- After confirmation: Use PerformAction with:
  - `actions`: ["update_communication_style", "stay"] to execute and stay on current node  
  - `communication_style_instruction`: A detailed instruction in Portuguese that captures exactly what the user requested, preserving all details
  - `messages`: Confirm the style update is being processed

**IMPORTANT for Communication Style:**
- The `communication_style_instruction` should be a complete instruction in Portuguese
- Preserve ALL details from the user's request - don't summarize or lose information
- The instruction will be APPENDED to the current communication style, not replace it
- Example: If user says "Fale de forma mais calorosa e use emojis de coração", the instruction should be: "Fale de forma mais calorosa e use emojis de coração em suas mensagens."

**Examples:**

**Example 1: Request with ambiguity (needs clarification)**
- Admin says: "Transfome todos as mensagens que tem mais de uma pergunta em varias perguntas separadas"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Analisei o fluxo e encontrei 3 nós com múltiplas perguntas:", "delay_ms": 0},
      {"text": "• q.inicio: 'Olá! Como posso ajudar? Qual seu interesse?' (saudação + intent)", "delay_ms": 1600},
      {"text": "• q.contato: 'Nome? Email? Telefone?' (coleta de dados)", "delay_ms": 1700},
      {"text": "• q.local: 'CEP? Número? Apartamento?' (endereço)", "delay_ms": 1800},
      {"text": "Devo dividir todos eles, ou apenas os de coleta de dados (q.contato e q.local), mantendo a saudação inicial intacta?", "delay_ms": 1500}
    ]

**Example 1b: Clear request (no clarification needed)**
- Admin says: "Divida o nó q.contato em perguntas separadas"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Entendi! Vou dividir o nó q.contato em 3 perguntas separadas: nome, email e telefone.", "delay_ms": 0},
      {"text": "As perguntas ficarão em sequência, mantendo o fluxo lógico.", "delay_ms": 1700},
      {"text": "Posso prosseguir com essa alteração?", "delay_ms": 1600}
    ]

**Example 2: After confirmation**
- Admin says: "Sim, pode fazer" or "Confirmo" or "Sim"
  → Use: PerformAction with actions=["modify_flow", "stay"], 
    flow_modification_instruction="Dividir todos os nós que têm múltiplas perguntas em nós separados com uma pergunta cada",
    messages=[{"text": "Perfeito! Estou processando a separação dos nós com múltiplas perguntas...", "delay_ms": 0}]

**Example 3: Admin clarifies it's an order (with confirmation)**
- Admin says: "Nao, isso foi uma ordem como admin pra quebrar o flow em 3 perguntas ao inves de uma só"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Ah, entendi! É uma ordem administrativa para modificar o fluxo.", "delay_ms": 0},
      {"text": "Vou dividir a pergunta atual em 3 perguntas separadas sequenciais.", "delay_ms": 1500},
      {"text": "Confirma que posso fazer essa alteração agora?", "delay_ms": 1600}
    ]

**Example 4: Direct modification request**
- Admin says: "Change this question to ask for their full name"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Ok! Vou alterar esta pergunta para solicitar o nome completo do usuário.", "delay_ms": 0},
      {"text": "Confirma essa modificação?", "delay_ms": 1500}
    ]

**Example 5: Admin cancels modification**
- Context: You just asked "Confirma essa modificação?"
- Admin says: "Não, deixa como está" or "Cancela"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Ok, sem problemas! Mantendo o fluxo como está.", "delay_ms": 0},
      {"text": "Continuando com a pergunta atual então...", "delay_ms": 1500},
      {"text": "[Repeat the current question from the flow]", "delay_ms": 1700}
    ]

**Example 6: Admin provides clarification after being asked**
- Context: You asked "Devo dividir todos, ou apenas os de coleta de dados?"
- Admin says: "Apenas os de coleta de dados, mantenha a saudação como está"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Perfeito! Vou manter o nó q.inicio intacto com a saudação.", "delay_ms": 0},
      {"text": "E vou dividir apenas q.contato (3 perguntas) e q.local (3 perguntas) em nós separados.", "delay_ms": 1500},
      {"text": "Total: 6 novos nós de coleta de dados. Posso prosseguir?", "delay_ms": 1700}
    ]

**Example 7: Admin provides different instructions after initial request**
- Context: Admin asked to split nodes, you asked for confirmation
- Admin says: "Na verdade, só divida este nó atual em 2 partes"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Ah, entendi! Mudando o plano então.", "delay_ms": 0},
      {"text": "Vou dividir apenas o nó atual em 2 perguntas separadas.", "delay_ms": 1500},
      {"text": "Confirma essa alteração?", "delay_ms": 1700}
    ]

**Example 8: Communication style change request**
- Admin says: "Fale de forma mais calorosa e use emojis"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Entendi! Vou ajustar o estilo de comunicação para ser mais caloroso e incluir emojis.", "delay_ms": 0},
      {"text": "Posso fazer essa alteração agora?", "delay_ms": 1500}
    ]

**Example 9: After confirming communication style change**
- Admin says: "Sim, pode fazer"
  → Use: PerformAction with actions=["update_communication_style", "stay"],
    communication_style_instruction="Fale de forma mais calorosa e acolhedora. Use emojis apropriados para tornar a conversa mais amigável e próxima.",
    messages=[{"text": "Perfeito! 😊 Ajustei o estilo de comunicação para ser mais caloroso com emojis!", "delay_ms": 0}]

**Example 10: Multiple communication instructions**  
- Admin says: "Não use emojis, seja mais direto e mande tudo numa mensagem só"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Ok! Vou remover emojis, ser mais direto e consolidar as respostas em uma única mensagem.", "delay_ms": 0},
      {"text": "Confirma essas mudanças no estilo de comunicação?", "delay_ms": 1500}
    ]
"""

    def _select_contextual_tools(
        self,
        context: FlowContext,
        pending_field: str | None,
        is_admin: bool = False,
    ) -> list[type]:
        """Select appropriate tools based on context.
        
        Note: Admin-only actions are controlled through prompting, not tool availability.
        The tool is always available but the prompt instructions restrict its use.
        """
        # Use PerformAction as the main tool - it can handle multiple actions
        from ..tools import PerformAction

        tools: list[type] = [
            PerformAction,  # Unified tool handles navigation, updates, handoff, admin modifications, and communication style
        ]

        return tools

    def _call_gpt5(
        self,
        instruction: str,
        tools: list[type],
        max_retries: int = MAX_SCHEMA_VALIDATION_RETRIES,
        context: FlowContext | None = None,
        pending_field: str | None = None,
        user_message: str = "",
        is_admin: bool = False,
        project_context: ProjectContext | None = None,
    ) -> GPT5Response:
        """Call GPT-5 with enhanced schema and retry on validation failures.

        Args:
            instruction: The prompt for GPT-5
            tools: Available tools for selection
            max_retries: Maximum retries for schema validation

        Returns:
            Validated GPT5Response

        Raises:
            GPT5SchemaError: If validation fails after retries
        """
        # Create enhanced schema that matches GPT5Response structure
        enhanced_schema = {
            "type": "object",
            "properties": {
                "tools": {
                    "type": "array",
                    "items": {"oneOf": [self._tool_to_schema(tool) for tool in tools]},
                    "minItems": 1,
                    "maxItems": 1,  # We only want one tool per response
                },
                "reasoning": {
                    "type": "string",
                    "description": "Overall reasoning for the response",
                },
            },
            "required": ["tools", "reasoning"],
        }

        last_exception = None
        for i in range(max_retries):
            try:
                self._llm_call_count += 1

                # Use the existing LLM interface - just call extract directly
                result = self._llm.extract(instruction, tools)

                # Convert the result to GPT5Response format if needed
                if isinstance(result, dict):
                    return self._convert_langchain_to_gpt5_response(result)
                # If it's already the right format, return it
                return result  # type: ignore[unreachable]

            except Exception as e:
                last_exception = e
                logger.warning(f"LLM call failed on attempt {i + 1}/{max_retries}: {e}")
                # Add error to instruction for retry
                error_summary = f"Error: {str(e)[:500]}"
                instruction += f"\n\n--- PREVIOUS ATTEMPT FAILED ---\nERROR: {error_summary}\nPlease try again with a valid response."

        error_msg = f"Failed to get a valid response after {max_retries} retries."
        raise GPT5SchemaError(
            message=error_msg,
            raw_response={},
            validation_errors=[str(last_exception)] if last_exception else [],
        ) from last_exception

    async def _process_gpt5_response(
        self,
        response: GPT5Response,
        context: FlowContext,
        pending_field: str | None,
        project_context: ProjectContext | None,
    ) -> ResponderOutput:
        """Process the validated GPT-5 response and execute tools."""
        # Get the primary tool (first tool in the list)
        primary_tool = response.tools[0] if response.tools else None
        if not primary_tool:
            # Fallback if no tools
            return self._create_fallback_response("No tools found in GPT-5 response")

        tool_name = primary_tool.tool_name

        # Convert tool to dict for the executor
        tool_data = primary_tool.model_dump()

        # Execute the tool
        # Create tool executor with action registry when needed
        from ..actions import ActionRegistry

        action_registry = ActionRegistry(self._llm)
        tool_executor = ToolExecutionService(action_registry)

        tool_result = await tool_executor.execute_tool(
            tool_name=tool_name,
            tool_data=tool_data,
            context=context,
            pending_field=pending_field,
        )

        # Extract messages from the tool (messages should be in the tool data)
        messages = tool_data.get(
            "messages", [{"text": "Erro ao processar mensagens", "delay_ms": 0}]
        )

        # Extract common fields from tool data for the final output
        reasoning = tool_data.get("reasoning", response.reasoning)
        confidence = tool_data.get("confidence", 0.8)

        return ResponderOutput(
            tool_name=tool_name,
            tool_result=tool_result,
            messages=messages,
            confidence=confidence,
            reasoning=reasoning,
        )

    def _tool_to_schema(self, tool: type) -> dict[str, Any]:
        """Convert a Pydantic model to a JSON schema for tool definition."""
        from pydantic import BaseModel

        if not issubclass(tool, BaseModel):
            raise TypeError("Tool must be a Pydantic BaseModel")

        # Get the schema directly from the model
        return tool.model_json_schema()  # type: ignore[no-any-return,attr-defined]

    def _convert_langchain_to_gpt5_response(self, langchain_result: dict[str, Any]) -> GPT5Response:
        """Convert LangChain tool result to GPT5Response format."""
        from ..flow_types import PerformActionCall

        # DEBUG: Log what we received from LangChain
        logger.info(f"[DEBUG] LangChain result: {json.dumps(langchain_result, indent=2)}")

        # Extract tool calls from LangChain result
        tool_calls = langchain_result.get("tool_calls", [])
        content = langchain_result.get("content", "")

        logger.info(f"[DEBUG] Extracted tool_calls: {tool_calls}")
        logger.info(f"[DEBUG] Extracted content: {content}")

        if not tool_calls:
            # Default to PerformAction with stay if no tool calls
            tool_call = PerformActionCall(
                tool_name="PerformAction",
                actions=["stay"],
                messages=[{"text": content or "Como posso ajudar?", "delay_ms": 0}],
                reasoning="No specific tool selected",
                confidence=0.5,
            )
            return GPT5Response(
                tools=[tool_call], reasoning="Processed user input without specific tool"
            )

        # Process the first tool call
        first_tool = tool_calls[0]
        tool_name = first_tool.get("name", "PerformAction")
        tool_args = first_tool.get("arguments", {})  # Changed from "args" to "arguments"

        logger.info(f"[DEBUG] Tool name: {tool_name}")
        logger.info(f"[DEBUG] Tool args: {json.dumps(tool_args, indent=2)}")

        # Ensure required fields are present
        if "reasoning" not in tool_args:
            tool_args["reasoning"] = f"Selected {tool_name}"
        if "confidence" not in tool_args:
            tool_args["confidence"] = 0.8
        if "messages" not in tool_args:
            # Generate default messages based on content
            logger.warning("[DEBUG] No messages found in tool_args! Using fallback.")
            tool_args["messages"] = [{"text": content or "Entendi!", "delay_ms": 0}]
        else:
            logger.info(f"[DEBUG] Found {len(tool_args['messages'])} messages in tool_args")

        # Create the appropriate tool call object
        if tool_name == "PerformAction":
            if "actions" not in tool_args:
                tool_args["actions"] = ["stay"]
            tool_call = PerformActionCall(**tool_args)
        else:
            # Fallback to PerformAction
            tool_call = PerformActionCall(
                tool_name="PerformAction",
                actions=["stay"],
                messages=tool_args.get("messages", [{"text": "Como posso ajudar?", "delay_ms": 0}]),
                reasoning=tool_args.get("reasoning", f"Unknown tool {tool_name}, staying on node"),
                confidence=tool_args.get("confidence", 0.3),
            )

        return GPT5Response(
            tools=[tool_call], reasoning=tool_args.get("reasoning", "Processed user input")
        )

    def _format_conversation_history(self, context: FlowContext) -> str:
        """Format the last N turns of conversation history."""
        if not context.history:
            return "No conversation history yet."

        formatted_history = []
        last_assistant_message = None

        for turn in context.history[-MAX_HISTORY_TURNS:]:
            # Handle both dict and object formats for conversation turns
            if hasattr(turn, "user_message") and hasattr(turn, "assistant_message"):
                # ConversationTurn object format
                formatted_history.append(f"User: {turn.user_message}")
                formatted_history.append(f"Assistant: {turn.assistant_message}")
                last_assistant_message = turn.assistant_message
            elif isinstance(turn, dict):
                # Dictionary format (fallback)
                formatted_history.append(f"User: {turn.get('user', '')}")
                assistant_msg = turn.get("assistant", "")
                formatted_history.append(f"Assistant: {assistant_msg}")
                if assistant_msg:
                    last_assistant_message = assistant_msg
            else:
                # Unknown format, try to extract content
                user_content = (
                    getattr(turn, "content", str(turn))
                    if hasattr(turn, "role") and turn.role == "user"
                    else ""
                )
                assistant_content = (
                    getattr(turn, "content", str(turn))
                    if hasattr(turn, "role") and turn.role == "assistant"
                    else ""
                )
                if user_content:
                    formatted_history.append(f"User: {user_content}")
                if assistant_content:
                    formatted_history.append(f"Assistant: {assistant_content}")
                    last_assistant_message = assistant_content

        # Add context about what the assistant is waiting for
        if last_assistant_message and "?" in last_assistant_message:
            formatted_history.append(
                "[CONTEXT: The assistant just asked a question and is waiting for an answer]"
            )

        return "\n".join(formatted_history)

    def _add_allowed_values_constraint(
        self, allowed_values: list[str] | None, pending_field: str | None
    ) -> str:
        """Add constraints for allowed values if applicable."""
        if allowed_values and pending_field:
            return f"""
### Constraint for '{pending_field}'
The value for the field '{pending_field}' MUST be one of the following: {", ".join(allowed_values)}.
Map the user's response to one of these exact values.
"""
        return ""

    def _create_fallback_response(self, error_message: str) -> ResponderOutput:
        """Create a fallback response in case of an unrecoverable error."""
        error_msg = f"Creating fallback response due to error: {error_message}"
        logger.error(error_msg)

        fallback_message: WhatsAppMessage = {"text": DEFAULT_ERROR_MESSAGE, "delay_ms": NO_DELAY_MS}

        return ResponderOutput(
            tool_name=None,
            tool_result=ToolExecutionResult(
                updates={},
                navigation=None,
                escalate=False,
                terminal=False,
                metadata={"error": error_message},
            ),
            messages=[fallback_message],
            confidence=0.0,
            reasoning=f"Fell back to safety response due to an internal error: {error_message[:100]}",
        )
