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
    get_golden_rule,
    get_identity_and_style,
    get_responsible_attendant_core,
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
        
        if not rag_documents or len(rag_documents) == 0:
            return """### Available Information from Tenant's Documents:
**NENHUM DOCUMENTO DISPONÍVEL**

Se o usuário perguntar sobre produtos/serviços/preços/especificações:
→ ESCALE IMEDIATAMENTE: actions=['handoff'], handoff_reason='information_not_available_in_documents'
→ Mensagem: "Deixa eu chamar alguém que tem essa informação certinha pra você, já volto!" (adapte ao estilo configurado)

Não diga "não sei" e fique parado. ESCALE para resolver a dúvida do usuário."""
        
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
                # Support both "kind" (new IR format) and "type" (legacy)
                node_types[node["id"]] = node.get("kind") or node.get("type", "unknown")
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
            if target_type in ("DecisionNode", "Decision"):
                # Show paths through the decision node
                next_nodes = edge_lookup.get(target, [])
                for next_node in next_nodes:
                    next_type = node_types.get(next_node, "unknown")
                    next_prompt = node_prompts.get(next_node, next_node)
                    if next_type not in ("DecisionNode", "Decision"):  # Skip nested routers
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
            is_admin=is_admin,
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

## RAG-RETRIEVED INFORMATION (Documentos do Tenant)
**O que é RAG:** Sistema de recuperação que busca trechos (chunks) relevantes dos documentos que o tenant fez upload (PDFs, catálogos, fichas técnicas, etc.). Quando o usuário pergunta algo, o sistema busca automaticamente nos documentos e traz apenas as partes relevantes para você responder.

**Como usar:** Se há informação abaixo, use ela. Se não há (seção vazia/sem documentos), ESCALE para humano resolver.

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
**PERGUNTA DO FLUXO QUE VOCÊ DEVE FAZER:**
Nó {context.current_node_id or "unknown"}: "{prompt}"

{"Coletando campo: " + pending_field if pending_field else ""}
{"Se você pediu algo e o usuário respondeu curto (número, sim/não), provavelmente é a resposta." if context.clarification_count > 0 else ""}
{"Você voltou de uma tarefa administrativa. Retome de forma natural, sem repetir igual." if context.history and len(context.history) > 0 and any("modify" in str(turn.metadata or {}) for turn in context.history[-3:]) else ""}
{"Conversa já andou bastante. Pule formalidades e vá direto ao ponto." if context.turn_count > 5 else ""}

REGRAS CRÍTICAS - FIDELIDADE AO FLUXO:

**VOCÊ DEVE FAZER A PERGUNTA DO FLUXO ACIMA. Este é o único objetivo da sua mensagem.**
**EXCEÇÃO: Se você está executando uma ação administrativa (modify_flow, update_communication_style), NÃO re-pergunte o prompt do nó atual. Apenas confirme a ação administrativa.**

**VOCÊ É UM ASSISTENTE CONDUZINDO UMA CONVERSA ESTRUTURADA, NÃO UM CHATBOT DE PERGUNTAS E RESPOSTAS.**

1. **SEMPRE conduza o fluxo ativamente**:
   - Sua missão principal: obter a informação que o nó atual precisa
   - Reescreva a pergunta naturalmente, mas mantenha o OBJETIVO idêntico
   - NÃO tenha conversas paralelas sobre assuntos fora do escopo do fluxo
   - NÃO apenas responda perguntas - SEMPRE conduza para a próxima etapa

2. **Quando o usuário pergunta SOBRE o domínio do fluxo (qualquer aspecto)**:
   - Qualquer pergunta sobre o tema do fluxo pode indicar interesse
   - Isso inclui: detalhes específicos, disponibilidade, capacidades, opções, processos, etc.
   - OBRIGATÓRIO: Responda brevemente usando RAG quando necessário e quando aplicável
   - OBRIGATÓRIO: Use a resposta como ponte natural para avançar o fluxo
   - **CRITICAL: NÃO repita o texto literal do prompt do nó - use o OBJETIVO do nó para criar uma ponte contextual**
   - Se o objetivo do nó é coletar informação, conecte a resposta à próxima etapa lógica
   - A ponte deve conectar organicamente: sua resposta → próximo passo lógico do fluxo
   - Use actions=["update", "navigate"] se houver informação completa OU actions=["stay"] se ainda estiver explorando
   - **CRITICAL: A conversa NUNCA para após responder - mantenha o fluxo avançando**
   - Regra de ouro: "Responder + Avançar Naturalmente" em uma única interação

3. **Quando o usuário fala sobre assuntos COMPLETAMENTE não relacionados ao fluxo**:
   - Aplica-se APENAS a tópicos externos: clima, hora, eventos pessoais, notícias, etc.
   - NÃO se aplica a perguntas sobre o tema ou domínio do fluxo
   - Reconheça educadamente e redirecione de forma natural e contextual
   - NUNCA use frases genéricas vazias como "Como posso te ajudar?"
   - A ponte deve ser específica ao objetivo do nó atual do fluxo
   - Use actions=["stay"] mantendo o nó atual

4. **Quando o usuário só cumprimenta ou fala de assuntos aleatórios**:
   - Reconheça brevemente de forma natural
   - Faça a pergunta do fluxo que o nó atual requer
   - Use actions=["stay"] mantendo o nó atual

5. **Reescrita natural** (não copie o texto do nó):
   - Adapte o tom e as palavras para soar conversacional
   - Mas mantenha exatamente o mesmo OBJETIVO da pergunta
   - Após interrupção/admin: "Voltando…" / "Agora me diz…"
   - Já cumprimentou? Pule o "Olá" e vá direto à pergunta
   - Segunda tentativa: mude bastante a forma de perguntar, mas o objetivo é o mesmo

Erros/typos do usuário:
- Se valor soar estranho, confirme com educação usando ["stay"]
- Ex.: "Só conferindo, são 4 metros mesmo?"

Confiança e confirmação:
- Alta (≥0.9): siga em frente sem confirmar
- Média (0.7–0.9): confirme rápido no meio da frase
- Baixa (<0.7): peça confirmação antes de prosseguir (use ["stay"]) 

Ferramenta: PerformAction (única disponível)
- **SEMPRE inclua o campo "messages" com 1–3 mensagens WhatsApp - SEM EXCEÇÕES**
- Campos obrigatórios: actions, messages, reasoning, confidence
- **CRITICAL: Campos condicionalmente obrigatórios (SEM EXCEÇÕES):**
  * Se actions contém "update": updates é OBRIGATÓRIO (dict com campo:valor)
    - Use o campo que está sendo coletado (veja "Coletando campo:" ou "pending_field" no ESTADO ATUAL)
    - CORRETO: actions=["update", "navigate"], updates={{"user_preference": "premium"}}
    - ERRADO: actions=["update"], updates=null ← ISTO CAUSA PERDA DE DADOS CRÍTICA!
    - ERRADO: actions=["update"], updates={{}} ← Vazio também perde dados!
  * Se actions contém "navigate": target_node_id é OBRIGATÓRIO
    - CORRETO: actions=["navigate"], target_node_id="q.next_question"
    - ERRADO: actions=["navigate"], target_node_id=null
  * Se actions contém "handoff": handoff_reason é OBRIGATÓRIO
  * Se actions contém "stay": clarification_reason é opcional
- Padrão comum: ["update", "navigate"] → SEMPRE inclua updates={{campo: valor}} E target_node_id
- **NUNCA use action="update" sem preencher o campo updates - isso perde a resposta do usuário!**
- **Se você não sabe qual valor salvar, use actions=["stay"] e peça clarificação**

**CRITICAL: MESSAGES FIELD IS ALWAYS MANDATORY**
- SEMPRE inclua messages com 1-3 mensagens, sem exceções
- **Comportamento de nós Decision (routers):**
  * Se você ESTÁ em um nó Decision (current_node_id começa com "d."):
    - Analise os AVAILABLE PATHS e o contexto do usuário
    - Escolha o caminho mais apropriado baseado no que o usuário disse
    - Envie mensagens do nó escolhido (do caminho mais apropriado).
    - Use actions=["navigate"] com target_node_id para o nó escolhido
  * Se você está NAVEGANDO PARA um nó Decision:
    - Isso não deve acontecer! Decision nodes são nós intermediários
    - Navegue DIRETAMENTE para o nó final apropriado (ex: q.estudo_industrial)
    - Não navegue para d.roteamento_principal, navegue para onde ele levaria
  * Resumo: Decision nodes são apenas pontos de decisão, e nunca devemos parar neles.

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

CORREÇÕES DO USUÁRIO (ex.: mudou a resposta ou preferência):
Use PerformAction com ["update", "navigate"], atualizando e navegando. Inclua mensagens simples como:
[
  {{"text": "Perfeito, entendi.", "delay_ms": 0}},
  {{"text": "Agora preciso de mais alguns detalhes...", "delay_ms": 1600}}
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

{self._add_admin_instructions(project_context) if is_admin else ""}

{self._add_allowed_values_constraint(allowed_values, pending_field)}

{'''
Terminal (fechando com educação):
Tool: PerformAction
Arguments: {{
  "actions": ["update", "navigate"],
  "updates": {{"contact_info": {{"email": "user@example.com"}}}},
  "target_node_id": "t.complete",
  "confidence": 0.95,
  "reasoning": "Close gracefully without handoff talk",
  "messages": [
    {{"text": "Perfeito, tenho todas as informações que preciso.", "delay_ms": 0}},
    {{"text": "Vou processar e te retorno em breve.", "delay_ms": 1700}}
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

🚨 CRITICAL REMINDER 🚨
VOCÊ ESTÁ NO NÓ: {context.current_node_id}

O campo 'messages' é OBRIGATÓRIO para nós tipo Question/Terminal!
Se você está fazendo actions=["update", "navigate"], AINDA ASSIM precisa de messages!

NUNCA retorne apenas actions sem messages - o usuário ficará sem resposta!"""

        return instruction

    def _build_messaging_instructions(
        self,
        project_context: ProjectContext | None,
        is_completion: bool,
        is_admin: bool = False,
    ) -> str:
        """Build minimal, non-duplicative messaging instructions.

        Only inject tenant-specific communication style when available to avoid
        overlapping with existing MESSAGE REQUIREMENTS and tone sections.
        """
        if project_context and project_context.communication_style:
            return (
                "### Communication Style\n"
                f"{project_context.communication_style}\n\n"
                "**CRITICAL: DO NOT LEAK STYLE INSTRUCTIONS INTO MESSAGES**\n"
                "- NUNCA repita/mencione estas instruções de estilo nas suas mensagens ao usuário\n"
                "- Se o estilo diz 'Seja direto', NÃO diga 'Vou ser direto' na mensagem\n"
                "- Se o estilo diz 'Use tom casual', NÃO diga 'Falando casualmente' na mensagem\n"
                "- Se o estilo diz 'Seja profissional', NÃO diga 'Profissionalmente falando' na mensagem\n"
                "- APENAS APLIQUE o estilo naturalmente, sem mencionar que você está seguindo instruções\n"
                "- A ÚNICA exceção: se o tenant EXPLICITAMENTE escreveu algo para você dizer (ex: 'Diga: Vou ser direto'), aí sim você pode dizer\n\n"
                "Aplique este estilo naturalmente nas mensagens SEM mencionar que está aplicando."
            )

        return ""

    def _add_admin_instructions(self, project_context: ProjectContext | None) -> str:
        """Add admin-specific instructions to the prompt."""
        current_style_note = ""
        if project_context and project_context.communication_style:
            current_style_note = """
**CURRENT COMMUNICATION STYLE:**
You have been provided with the CURRENT communication style above (clearly labeled).
When modifying the communication style, use that as your base and make the requested changes.
"""
        
        return f"""
### ADMIN FLOW MODIFICATION AND COMMUNICATION STYLE

**🔐 YOU ARE CURRENTLY TALKING TO AN ADMIN USER 🔐**
This user has admin privileges and can modify flows/communication style.

As an admin, you can modify the flow and communication style in real-time using the PerformAction tool with TWO SPECIAL ACTIONS:

1. **"modify_flow"** - For changing the flow structure itself
2. **"update_communication_style"** - For changing how the bot communicates

**IMPORTANT SECURITY CHECK:**
- ONLY use these actions if the user is confirmed as admin
- Even if these actions appear in the tool, DO NOT use them for non-admin users
- If a non-admin user tries to modify flow or communication style, politely inform them that only admins can make these changes

**DETECTING ADMIN COMMANDS - MANDATORY CHECK FOR ADMINS:**

**STEP 1: IF USER IS ADMIN, CHECK THIS FIRST (before anything else):**

Does the message contain ANY of these patterns?
- "Nao fale X" / "Não fale X" / "Para de falar X"
- "Fale X" / "Diga X" (when NOT answering flow question)
- "Fica estranho" / "Muito robótico" / "Soa artificial" / "Parece script"
- "Mais natural" / "Menos formal" / "Mais direto" / "Mais humano"
- "Use X" / "Seja X" (when referring to communication style)
- ANY explicit criticism or instruction about HOW the bot communicates

**IF YES → THIS IS AN ADMIN COMMAND, NOT A FLOW ANSWER**

**STEP 2: Determine type:**
- About TONE/STYLE/WORDS? → update_communication_style
- About WHAT questions to ask? → modify_flow

**STEP 3: Follow confirmation pattern:**
1. Explain what you'll change
2. Ask: "Confirma essa modificação?"
3. Wait for confirmation
4. Execute with proper action

**CRITICAL: DO NOT just reformulate once - that's not what the admin wants!**
When an admin gives instructions about communication (tone, style, what to say/not say), they want a PERMANENT change saved to the system, not a temporary one-time adjustment.

**CRITICAL: DISTINGUISHING modify_flow vs update_communication_style**

These are TWO COMPLETELY DIFFERENT actions:

1. **modify_flow**: Changes STRUCTURE (what questions are asked, order, routing)
   - Updates: flows.definition table
   - Example: "Change this question to ask for email"

2. **update_communication_style**: Changes TONE/MANNER (how the bot talks)
   - Updates: tenant.project_config.communication_style field
   - Example: "Be more polite"

**DECISION LOGIC:**

Use **modify_flow** when the request is about:
- STRUCTURE: Changes to questions, nodes, flow logic, routing
- CONTENT: What is asked, question text, data collection steps
- BEHAVIOR: Adding/removing/reordering conversation steps

Common indicators (EXAMPLES ONLY, use your semantic understanding):
- Words like "pergunta", "question", "nó", "node", "passo", "step"
- Actions like "adicionar", "add", "remover", "remove", "dividir", "split"
- But even without these keywords, if it's changing the STRUCTURE → modify_flow

Examples:
  ✓ "Change the greeting question to ask for their name"
  ✓ "Mude esta pergunta para pedir o email"
  ✓ "Adicione uma pergunta sobre telefone"
  ✓ "Divida este nó em duas perguntas"
  ✓ "Remova a pergunta sobre endereço"
  ✓ "Mude a saudação para PERGUNTAR o nome primeiro"

Use **update_communication_style** when the request is about:
- TONE: How the bot sounds (formal, casual, warm, professional)
- PERSONALITY: Character traits (friendly, direct, polite, enthusiastic)
- PRESENTATION: How messages are formatted (emoji usage, length, word choice)

Common indicators (EXAMPLES ONLY, use your semantic understanding):
- Words like "tom", "tone", "estilo", "style", "jeito", "manner"
- Traits like "formal", "informal", "caloroso", "educado", "direto"
- Presentation like "emoji", "conciso", "detalhado", "curto", "longo"
- But even without these keywords, if it's changing HOW it communicates → update_communication_style

Examples:
  ✓ "Seja mais educado"
  ✓ "Use mais/menos emojis"
  ✓ "Da uma maneirada nos emojis"
  ✓ "Fale de forma mais direta"
  ✓ "Seja mais profissional no tom"
  ✓ "Mude o tom da saudação para SER MAIS CALOROSO"
  ✓ "Fale mais como uma pessoa, menos robótico"

For **ambiguous phrases**, use semantic understanding to analyze intent:
- "Mude a saudação para [perguntar X]" → modify_flow (changing the question itself or the intention)
- "Mude a saudação para [ser mais calorosa]" → update_communication_style (changing the tone)
- "Termine as mensagens com [uma pergunta]" → modify_flow (adding a structural element)
- "Termine as mensagens com ['Abraço!']" → update_communication_style (changing closing style)

**FUNDAMENTAL TEST (always rely on this):**
- Is the request about WHAT content/questions/intention are presented? → modify_flow
- Is the request about HOW content is presented/communicated? → update_communication_style

Don't just match keywords - understand the SEMANTIC INTENT of the request.

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
  - `flow_modification_instruction`: Natural language instruction for the modification (Portuguese)
  - `flow_modification_target` (optional): The ID of the specific node to modify
  - `flow_modification_type` (optional): Can be "prompt", "routing", "validation", or "general"
  - `messages`: Confirm the modification is being processed
  
**CRITICAL - Messages after admin actions:**
- When executing modify_flow or update_communication_style, your messages should ONLY:
  1. Acknowledge that the modification is being applied
  2. Confirm completion (e.g., "Ajustando nós e rotas agora")
- DO NOT ask the current node's question again
- DO NOT say things like "Como posso te ajudar hoje?" after an admin action
- The flow will naturally resume after the modification is complete
- Keep messages focused on the administrative task, not on resuming flow questions

**For Communication Style Changes:**
{current_style_note}
When an admin requests communication style changes:
- First time (no confirmation): Use PerformAction with actions=["stay"], explain changes, ask for confirmation
- After confirmation: Use PerformAction with:
  - `actions`: ["update_communication_style", "stay"] to execute and stay on current node
  - `updated_communication_style`: The COMPLETE new communication style in Portuguese
  - `messages`: Confirm the style update is being processed (see CRITICAL note above about messages)

**CRITICAL for Communication Style:**
- You will receive the CURRENT communication style in context (clearly labeled)
- Take the CURRENT style as your starting point
- Apply ONLY the admin's requested changes - be PRECISE and MINIMAL
- **DO NOT add extra instructions** that weren't requested
- **BE REACTIVE, NOT PROACTIVE** - if admin asks for A, change A only, not A + B + C
- **WRITE IN THE SAME LANGUAGE as the conversation** - if chat is in Portuguese, write in Portuguese
- The `updated_communication_style` field should contain the FULL style (not just changes)
- This will REPLACE the current style entirely
- Keep it minimal - only change what was explicitly requested, preserve everything else

**CRITICAL: Communication style is about TONE and STYLE, NOT operational rules:**
- Communication style = HOW to talk (tone, formality, emoji usage, warmth, directness)
- **DO NOT copy system instructions** like "Use RAG", "Follow the flow", "Don't invent"
- **DO NOT include operational rules** - those are already in the system
- Only include TONE and STYLE guidance that changes how messages sound to users
- Examples of valid style: "Tom caloroso", "Seja direto", "Use emojis", "Mais formal"
- Examples of INVALID (system instructions): "Use apenas RAG", "Siga o fluxo", "Não invente"

**Examples:**

**Example 1: Request with ambiguity (needs clarification)**
- Admin says: "Transfome todos as mensagens que tem mais de uma pergunta em varias perguntas separadas"
  → Use: PerformAction with actions=["stay"], messages=[
      {{"text": "Analisei o fluxo e encontrei 3 nós com múltiplas perguntas:", "delay_ms": 0}},
      {{"text": "• q.inicio: 'Olá! Como posso ajudar? Qual seu interesse?' (saudação + intent)", "delay_ms": 1600}},
      {{"text": "• q.contato: 'Nome? Email? Telefone?' (coleta de dados)", "delay_ms": 1700}},
      {{"text": "• q.local: 'CEP? Número? Apartamento?' (endereço)", "delay_ms": 1800}},
      {{"text": "Devo dividir todos eles, ou apenas os de coleta de dados (q.contato e q.local), mantendo a saudação inicial intacta?", "delay_ms": 1500}}
    ]

**Example 1b: Clear request (no clarification needed)**
- Admin says: "Divida o nó q.contato em perguntas separadas"
  → Use: PerformAction with actions=["stay"], messages=[
      {{"text": "Entendi! Vou dividir o nó q.contato em 3 perguntas separadas: nome, email e telefone.", "delay_ms": 0}},
      {{"text": "As perguntas ficarão em sequência, mantendo o fluxo lógico.", "delay_ms": 1700}},
      {{"text": "Posso prosseguir com essa alteração?", "delay_ms": 1600}}
    ]

**Example 2: After confirmation**
- Admin says: "Sim, pode fazer" or "Confirmo" or "Sim"
  → Use: PerformAction with actions=["modify_flow", "stay"], 
    flow_modification_instruction="Dividir todos os nós que têm múltiplas perguntas em nós separados com uma pergunta cada",
    messages=[{{"text": "Perfeito! Estou processando a separação dos nós com múltiplas perguntas...", "delay_ms": 0}}]

**Example 3: Admin clarifies it's an order (with confirmation)**
- Admin says: "Nao, isso foi uma ordem como admin pra quebrar o flow em 3 perguntas ao inves de uma só"
  → Use: PerformAction with actions=["stay"], messages=[
      {{"text": "Ah, entendi! É uma ordem administrativa para modificar o fluxo.", "delay_ms": 0}},
      {{"text": "Vou dividir a pergunta atual em 3 perguntas separadas sequenciais.", "delay_ms": 1500}},
      {{"text": "Confirma que posso fazer essa alteração agora?", "delay_ms": 1600}}
    ]

**Example 4: Direct modification request**
- Admin says: "Change this question to ask for their full name"
  → Use: PerformAction with actions=["stay"], messages=[
      {{"text": "Ok! Vou alterar esta pergunta para solicitar o nome completo do usuário.", "delay_ms": 0}},
      {{"text": "Confirma essa modificação?", "delay_ms": 1500}}
    ]

**Example 5: Admin cancels modification**
- Context: You just asked "Confirma essa modificação?"
- Admin says: "Não, deixa como está" or "Cancela"
  → Use: PerformAction with actions=["stay"], messages=[
      {{"text": "Ok, sem problemas! Mantendo o fluxo como está.", "delay_ms": 0}},
      {{"text": "Continuando com a pergunta atual então...", "delay_ms": 1500}},
      {{"text": "[Repeat the current question from the flow]", "delay_ms": 1700}}
    ]

**Example 6: Admin provides clarification after being asked**
- Context: You asked "Devo dividir todos, ou apenas os de coleta de dados?"
- Admin says: "Apenas os de coleta de dados, mantenha a saudação como está"
  → Use: PerformAction with actions=["stay"], messages=[
      {{"text": "Perfeito! Vou manter o nó q.inicio intacto com a saudação.", "delay_ms": 0}},
      {{"text": "E vou dividir apenas q.contato (3 perguntas) e q.local (3 perguntas) em nós separados.", "delay_ms": 1500}},
      {{"text": "Total: 6 novos nós de coleta de dados. Posso prosseguir?", "delay_ms": 1700}}
    ]

**Example 7: Admin provides different instructions after initial request**
- Context: Admin asked to split nodes, you asked for confirmation
- Admin says: "Na verdade, só divida este nó atual em 2 partes"
  → Use: PerformAction with actions=["stay"], messages=[
      {{"text": "Ah, entendi! Mudando o plano então.", "delay_ms": 0}},
      {{"text": "Vou dividir apenas o nó atual em 2 perguntas separadas.", "delay_ms": 1500}},
      {{"text": "Confirma essa alteração?", "delay_ms": 1700}}
    ]

**Example 8: Communication style change request**
- Admin says: "Fale de forma mais calorosa e use emojis"
  → Use: PerformAction with actions=["stay"], messages=[
      {{"text": "Entendi! Vou ajustar o estilo de comunicação para ser mais caloroso e incluir emojis.", "delay_ms": 0}},
      {{"text": "Posso fazer essa alteração agora?", "delay_ms": 1500}}
    ]

**Example 9: After confirming communication style change**
- Admin says: "Sim, pode fazer"
  → Use: PerformAction with actions=["update_communication_style", "stay"],
    updated_communication_style="Fale de forma mais calorosa e acolhedora. Use emojis apropriados para tornar a conversa mais amigável e próxima.",
    messages=[{{"text": "Perfeito! 😊 Ajustei o estilo de comunicação para ser mais caloroso com emojis!", "delay_ms": 0}}]

**Example 10: Multiple communication instructions**  
- Admin says: "Não use emojis, seja mais direto e mande tudo numa mensagem só"
  → Use: PerformAction with actions=["stay"], messages=[
      {{"text": "Ok! Vou remover emojis, ser mais direto e consolidar as respostas em uma única mensagem.", "delay_ms": 0}},
      {{"text": "Confirma essas mudanças no estilo de comunicação?", "delay_ms": 1500}}
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
        from ..tools import PerformAction

        tools: list[type] = [
            PerformAction,
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
        return tool.model_json_schema()

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
            logger.error("[BUG] LLM did not include 'messages' field! This should never happen.")
            tool_args["messages"] = [{"text": content or "⚠️ Erro interno: resposta sem mensagem. Contate o administrador.", "delay_ms": 0}]
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
            if turn.role == "user":
                formatted_history.append(f"User: {turn.content}")
            elif turn.role == "assistant":
                formatted_history.append(f"Assistant: {turn.content}")
                last_assistant_message = turn.content
            elif turn.role == "system":
                formatted_history.append(f"System: {turn.content}")

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
