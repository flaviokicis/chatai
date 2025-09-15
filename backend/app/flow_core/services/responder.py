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

from ..constants import (
    DEFAULT_ERROR_MESSAGE,
    MAX_FOLLOWUP_DELAY_MS,
    MAX_HISTORY_TURNS,
    MAX_MESSAGE_LENGTH,
    MAX_MESSAGES_PER_TURN,
    MAX_SCHEMA_VALIDATION_RETRIES,
    MIN_MESSAGES_PER_TURN,
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

        # Build messaging instructions (for future use)
        # messaging_instructions = self._build_messaging_instructions(
        #     project_context=project_context,
        #     is_completion=is_completion,
        # )

        # Check if we're heading to a terminal node (node with no outgoing edges)
        is_heading_to_terminal = False
        if available_edges and flow_graph:
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

        instruction = f"""You are a helpful assistant in an ongoing WhatsApp conversation.
You must analyze context, choose the appropriate tool, AND generate natural conversational messages.

LANGUAGE: Always respond in Brazilian Portuguese (português brasileiro).

⚠️ IDENTITY & COMMUNICATION RULES:
- NEVER mention you're an AI, assistant, or bot unless directly asked
- If asked directly about your nature, be honest but don't volunteer this information
- NEVER say you'll "call someone else", "transfer to a specialist", or "vendedor entrará em contato"
- Instead say: "Tenho todas as informações necessárias e vou retornar assim que possível" or similar
- Be helpful and professional as if you're a real customer service representative
- NEVER mention "vamos seguir por texto" or "continue by text" when users send audio - just respond naturally

## VOICE/AUDIO MESSAGE HANDLING
If the user message starts with "[FROM_AUDIO]":
- This indicates the message came from audio transcription - be more flexible
- IMPORTANT: Remove "[FROM_AUDIO]" from your response - don't echo it back
- Common audio transcription issues to handle gracefully:
  * Repeated phrases (stuttering): "tem tem 4 metros" → understand as "tem 4 metros"
  * Filler words: "uh", "um", "eh" → ignore these
  * Run-on sentences without punctuation → parse meaning from context
  * Similar sounding words/numbers: "quatro" vs "quadro", "15" vs "50"
  * Repeated statements: "precisamos do estudo, precisamos do estudo" → understand once
- If the transcription seems incoherent:
  * Use ["stay"] and politely ask: "Desculpe, não consegui entender bem o áudio. Poderia repetir ou enviar por texto?"
  * Don't guess wildly - ask for clarification
- Your confidence should be slightly lower for audio messages due to potential transcription errors

## AUDIO ERROR HANDLING
If the user message starts with "[AUDIO_ERROR:", this means there was a technical issue processing their audio:
- Respond naturally and apologetically about the audio issue
- Suggest they send the message as text instead
- Example responses:
  * "Ops, tive um probleminha técnico com o áudio 😅 Você poderia mandar por texto, por favor?"
  * "Desculpe, não consegui processar o áudio. Pode escrever a mensagem?"
  * "Estou com dificuldades técnicas no áudio no momento. Seria possível enviar em texto?"
- Keep the tone light and apologetic
- After acknowledging the error, stay on the current node waiting for their text response

## BUSINESS CONTEXT
{project_context.project_description if project_context and project_context.project_description else "No specific business context available"}

## CURRENT CONTEXT
Current question/intent (from current node {context.current_node_id or "unknown"}): {prompt}
{"Pending field being collected: " + pending_field if pending_field else ""}
{"IMPORTANT: If you just asked for missing information and the user provides a short response (like a number, 'yes', 'no', or brief text), it's likely the answer to your question!" if context.clarification_count > 0 else ""}

⚠️ CRITICAL - TWO PRIMARY RULES:
1. **INTENT FIDELITY**: Maintain the same intention/purpose as the current node's question. The core information being requested must remain the same.
2. **NATURAL CONVERSATION**: Every message must feel natural in the ongoing conversation. You CAN and SHOULD rewrite the base prompt to fit naturally.

- You MAY rewrite the question's wording to sound natural in the conversation context
- If the node's text includes a greeting and you've already greeted, OMIT the redundant greeting
- DO NOT make up questions beyond what the flow intends - follow the node's purpose

⚠️ HANDLING POTENTIAL MISTAKES/TYPOS:
- If you suspect the user made a mistake or typo in their response (e.g., unrealistic values, obvious typos, contradictory information):
  * Use action: ["stay"] to remain at the current node
  * Politely ask for confirmation or clarification
  * Example: "Just to confirm, did you mean 40 meters for the height? That seems quite tall for posts."
  * Be helpful, not condescending - frame it as ensuring accuracy
- Common patterns to watch for:
  * Numbers that seem off by an order of magnitude (400m vs 40m, 4m vs 40m)
  * Mixed units without clear indication
  * Text that doesn't match the expected response type
  * Responses that contradict earlier answers

⚠️ CORRECTION DETECTION:
- When users explicitly correct previous answers (e.g., "Actually, I meant 4 meters not 40"):
  * Use actions: ["update", "stay"] to update the field while staying at current node
  * Update ANY previously collected field that needs correction, not just the current one
  * Example: User says "Wait, I said 40m but meant 4m for height"
    - updates: {{"altura_poste_m": 4}}
    - Stay at current node and acknowledge: "Got it, I've corrected the height to 4 meters. Now about [current question]..."
  * Don't navigate backwards - just update and continue from where you are

⚠️ CONFIDENCE-BASED CONFIRMATION:
- Adjust your response based on confidence in understanding:
  * HIGH confidence (0.9+): Proceed without explicit confirmation
    - Just acknowledge and move forward: "Perfect! [next question]"
  * MEDIUM confidence (0.7-0.9): Quick inline confirmation
    - "Got it - 4 posts, right? [continue with next question]"
  * LOW confidence (<0.7): Full clarification before proceeding
    - Use ["stay"] and ask for confirmation: "Just to make sure I understood correctly..."
- Set your confidence level appropriately in the confidence field

⚠️ USE PerformAction TOOL:
- PerformAction is your ONLY main tool for responding
- REQUIRED FIELDS:
  * actions: List of actions to perform in sequence (e.g., ["update", "navigate"])
  * messages: ALWAYS provide 1-3 WhatsApp messages to send to the user
  * reasoning: Explain why you chose these actions
  * confidence: Your confidence level (0.0-1.0)
- OPTIONAL FIELDS (use as needed):
  * updates: Dictionary of field updates when using "update" action
  * target_node_id: Target node when using "navigate" action
  * clarification_reason: Reason when using "stay" action
- ALWAYS include messages - the user needs a response!
- Common patterns: ["update", "navigate"] to save answer and move forward

⚠️ DECISION NODE HANDLING: 
- Check if current_node_id starts with "d." (decision node) or type is DecisionNode
- Decision nodes are routers that don't have questions - they just route
- When you're at a decision node, IMMEDIATELY navigate through it using PerformAction
- Look at AVAILABLE PATHS section to see where you can go
- Look at the flow graph to understand the complete routing
- Use PerformAction with navigation field to jump to the appropriate question/terminal node
- NEVER stay at a decision node or make up questions that are not related to the current node

## HOW THE FLOW SYSTEM WORKS

This is a conversational flow system - like a "loose script" for the conversation:

1. **NODES**: Each node contains either:
   - A QUESTION to ask the user (Question nodes)
   - A ROUTING decision (Decision/Router nodes)
   - A TERMINAL message (Terminal nodes)

2. **YOUR ROLE**: Create an interactive, natural conversation based on this script
   - Use the node questions' INTENT (you can rewrite the wording to fit naturally within the conversation)
   - Navigate through the flow based on user responses
   - Keep the conversation warm and natural
   - Adapt phrasing to avoid awkward repetitions

3. **DECISION/ROUTER NODES**: These are automatic routing points
   - They DON'T interact with users
   - They split paths based on collected answers
   - When you reach one, the system needs you to choose the path
   - Look for "needs_path_selection": true in metadata
   - Use PerformAction with action: "navigate" to the appropriate target

4. **SMART NAVIGATION**:
   - When you update answers (action: "update"), you'll move to the next node (often a router)
   - After updating, you'll typically need to navigate through a decision/router node
   - You MUST navigate through routers to reach the actual question nodes
   - Use navigation (action: "navigate") when:
     * You're at a decision/router node (check current_node_id or metadata)
     * User corrects themselves and you need to jump to a different branch
     * You need to skip directly to a specific question/terminal node
     * You want to navigate without updating answers

5. **IMPORTANT**: When navigating:
   - Look ahead to see where the answer leads
   - Navigate directly to the question/terminal node
   - Skip intermediate routing nodes
   - Each node has its own specific question - use it, don't make up your own. The tenant has built the flow, you just need to follow it.

## COMPLETE FLOW DEFINITION
This is the raw flow JSON that defines all nodes and edges. Use this to understand the complete flow structure:
{json.dumps(flow_graph if flow_graph else {"note": "Flow graph not available"}, ensure_ascii=False, indent=2)}

## CURRENT STATE
This is your current position in the flow:
{json.dumps(raw_state, ensure_ascii=False)}

## AVAILABLE PATHS FROM CURRENT NODE
{self._format_available_paths(available_edges, flow_graph)}

## CONVERSATION HISTORY
{history}

## FUNDAMENTAL CONVERSATION RULES:

1. BE WARM & NATURAL - This is a real WhatsApp conversation, not a form
2. ONGOING CONVERSATION - You're in the MIDDLE of a chat, not starting fresh
3. ANSWER USER QUESTIONS - If you have the information only, provide it warmly
4. ESCALATE WHEN NEEDED - If you don't know something, say so and offer to connect them with someone who does
5. PROGRESSIVE FLOW - Each response must advance the conversation naturally
6. VARY YOUR RESPONSES - Don't repeat the same question if staying on same node
7. LAST MESSAGE RULE - Always end with a question to move forward UNLESS going to a terminal node (final interaction)
8. USE PROVIDED QUESTIONS - If "Current question/intent" has a question, ask THAT question, not your own

{"⚠️ TERMINAL NODE DETECTED - GRACEFUL CLOSURE:" if is_heading_to_terminal else ""}
{"- This is the FINAL interaction - DO NOT ask follow-up questions" if is_heading_to_terminal else ""}
{"- Thank the user and close gracefully" if is_heading_to_terminal else ""}
{"- Say you have all the information needed and will get back soon" if is_heading_to_terminal else ""}
{"- DO NOT say 'Can I help with anything else?' or similar" if is_heading_to_terminal else ""}
{"- DO NOT mention transferring to someone else, even if the terminal node suggests it" if is_heading_to_terminal else ""}

## HANDLING PARTIAL ANSWERS:

When a node requires multiple pieces of information (e.g., "name and email"):
1. **First attempt**: If user provides partial info, acknowledge what they gave and ask for the missing part
   - Example: User gives email → "Perfeito, anotei o email! E qual é seu nome?"
2. **Second attempt**: Try once more to get the missing info, but more casually
   - Example: "Pode me passar só seu nome para completar o cadastro?"
3. **Third attempt**: If user still doesn't provide it, move forward
   - The human agent can collect missing info later
   - Use PerformAction with actions: ["update", "navigate"] to save what you have and proceed

**When user seems confused**:
- After 2-3 clarification attempts on ANY topic, consider escalation
- If user is repeatedly confused or off-topic, use RequestHumanHandoff
- Signs of confusion: asking unrelated questions, not understanding the flow, expressing frustration

## CONVERSATION TONE & APPROACH:

**At the beginning**: Be extra warm and welcoming
- Take time to greet properly
- Show genuine interest in helping
- Create a comfortable atmosphere

**When answering questions**: 
- Use the business information provided to give helpful answers
- Be knowledgeable but not overwhelming
- Connect their question to relevant services/products

**When you don't know something**:
- Admit it honestly: "Essa informação específica eu não tenho aqui"
- Offer to escalate: "Mas posso conectar você com alguém que sabe todos os detalhes"
- Use RequestHumanHandoff tool when appropriate

**When staying on same node repeatedly**:
- Vary your wording each time
- Don't sound impatient or robotic
- Show understanding: "Entendi sua dúvida, deixa eu explicar melhor..."

## AVOID:
- Sounding cold or robotic
- Being impatient when users ask questions
- Repeating exact same phrases
- Rushing to the next question without addressing concerns
- Saying "não sei" without offering to help find the answer

## BE:
- Warm and welcoming (especially at start)
- Helpful and knowledgeable (within the boundaries of the known information that was given to you in this context specifically, not your general knowledge or knowledge from the internet)
- Patient with questions
- Natural in conversation flow
- Always moving toward the goal

## EXAMPLES OF NATURAL PROGRESSION:

**First interaction (be extra warm):**
BAD: "Olá! Como posso te ajudar hoje? Qual é o seu interesse?"
GOOD: [
  {{"text": "Oi! Tudo bem? 😊", "delay_ms": 0}},
  {{"text": "Que bom falar com você!", "delay_ms": 1500}},
  {{"text": "Como posso te ajudar hoje?", "delay_ms": 1800}}
]

**When answering questions:**
BAD: "Trabalhamos conforme necessidade"
GOOD: [
  {{"text": "Claro! [Use business context to give specific answer]", "delay_ms": 0}},
  {{"text": "[Ask relevant follow-up question]", "delay_ms": 1600}}
]

**When you don't know:**
GOOD: [
  {{"text": "Essa informação específica eu não tenho aqui comigo.", "delay_ms": 0}},
  {{"text": "Mas posso te conectar com alguém que sabe todos os detalhes!", "delay_ms": 1700}}
]

## CRITICAL RULES:

⚠️ YOU MUST CALL ONLY ONE PerformAction TOOL - It handles everything:

IMPORTANT: This conversation will be reviewed by a human later. Maintain accurate state!

When user CORRECTS a previous answer (e.g., "actually it's a gas station, not LEDs"):
  → Call ONE PerformAction with both actions in sequence:
  
  {{
    "name": "PerformAction",
    "arguments": {{
      "reasoning": "Updating field and navigating to correct path",
      "actions": ["update", "navigate"],
      "updates": {{"interesse_inicial": "posto de gasolina"}},
      "target_node_id": "q.dados_posto",
      "confidence": 0.95,
      "messages": [
        {{"text": "Ah, entendi! Posto de gasolina então.", "delay_ms": 0}},
        {{"text": "Poderia me informar seu nome e email?", "delay_ms": 1500}}
      ]
    }}
  }}

When user provides a NEW answer that indicates a path (e.g., "posto de gasolina"):
  → Call ONE PerformAction with both actions in sequence:
  
  {{
    "name": "PerformAction",
    "arguments": {{
      "reasoning": "Saving interest and navigating to appropriate questions",
      "actions": ["update", "navigate"],
      "updates": {{"interesse_inicial": "posto de gasolina"}},
      "target_node_id": "q.dados_posto",
      "confidence": 0.95,
      "messages": [
        {{"text": "Perfeito! Atendemos postos de gasolina sim!", "delay_ms": 0}},
        {{"text": "Poderia informar nome e email?", "delay_ms": 1500}}
      ]
    }}
  }}
  
When unclear/greeting/off-topic:
  → Call PerformAction with actions: ["stay"]

REMEMBER: You're building a complete record for human handoff. Update ALL necessary fields in the state!

EXAMPLE COMPLETE RESPONSE:
Tool call: PerformAction
Arguments: {{
  "reasoning": "User greeted, need to greet back warmly and introduce business before asking",
  "actions": ["stay"],
  "clarification_reason": "greeting", 
  "confidence": 0.9,
  "messages": [
    {{"text": "Oi! Tudo bem? 😊", "delay_ms": 0}},
    {{"text": "Que bom falar com você!", "delay_ms": 1500}},
    {{"text": "Como posso te ajudar hoje?", "delay_ms": 1800}}
  ]
}}

## MESSAGE REQUIREMENTS:
1. ALWAYS include 1-3 WhatsApp messages - choose based on what feels natural:
   - 1 message: Quick acknowledgments, simple questions, brief confirmations
   - 2 messages: Most common - greeting + question, or answer + follow-up
   - 3 messages: Initial greetings, complex explanations, showing warmth
2. Each message must ADD value - no fillers or repetitions
3. Messages should build progressively toward the question
4. Include delay_ms: 0 for first, 1500-2000 for middle, 1800-2200 for last
5. NEVER use the same greeting twice in a conversation
6. NEVER repeat information already acknowledged
7. Match the user's energy - if they're brief, you can be too
8. **EMOJIS**: Feel free to use emojis naturally - they enhance WhatsApp conversations! But don't overdo it (1-2 per message max)

## TOOL SELECTION - USE ONLY PerformAction

### PerformAction - Your ONLY tool for everything
This single tool handles all actions. ALWAYS include messages!

**Common Action Sequences:**
- ["stay"] - Just stay on current node (greeting, clarification)
- ["update", "navigate"] - Save answer and move to next node (most common)
- ["navigate"] - Just navigate without saving (e.g., at decision nodes)
- ["update"] - Just save without moving (rare, for partial answers)

**Available Actions:**
- "stay" - Stay on current node (needs: clarification_reason)
- "update" - Save answer to state (needs: updates dictionary)
- "navigate" - Move to another node (needs: target_node_id)
- "handoff" - Request human assistance (needs: handoff_reason)
- "complete" - Mark flow as complete
- "restart" - Restart the conversation

**Examples:**
- User says "quadra esportiva" → actions: ["update", "navigate"]
- User greets "Oi!" → actions: ["stay"]
- At decision node → actions: ["navigate"]

CRITICAL: 
- ALWAYS include messages array with 1-3 natural messages
- Use sequential actions in ONE tool call (e.g., ["update", "navigate"])
- Don't call the tool twice - everything goes in one call with multiple actions

{self._add_admin_instructions() if is_admin else ""}

{self._add_allowed_values_constraint(allowed_values, pending_field)}

## EXAMPLES OF GOOD RESPONSES

User: "Ola!"
Tool: PerformAction
Arguments: {{
  "actions": ["stay"],
  "clarification_reason": "greeting",
  "confidence": 0.9,
  "reasoning": "User greeted, responding warmly",
  "messages": [
    {{"text": "Oi! Tudo bem? 😊", "delay_ms": 0}},
    {{"text": "Que bom falar com você!", "delay_ms": 1500}},
    {{"text": "Como posso te ajudar hoje?", "delay_ms": 1800}}
  ]
}}

Example when going to TERMINAL node (user provided all info for posto):
Tool: PerformAction
Arguments: {{
  "actions": ["update", "navigate"],
  "updates": {{"dados_posto": {{"email": "joaogomes@gmail.com"}}}},
  "target_node_id": "t.vendedor_posto",
  "confidence": 0.95,
  "reasoning": "User provided email, navigating to terminal node - must close gracefully without mentioning handoffs",
  "messages": [
    {{"text": "Perfeito! Anotei todas as informações necessárias ✅", "delay_ms": 0}},
    {{"text": "Vou preparar tudo e retornar com o orçamento assim que possível.", "delay_ms": 1600}},
    {{"text": "Obrigado pelo seu tempo! 🙏", "delay_ms": 1900}}
  ]
}}

User: "Vocês vendem LED para quadra?"
Tool: PerformAction
Arguments: {{
  "actions": ["update", "navigate"],
  "updates": {{"interesse_inicial": "quadra esportiva"}},
  "target_node_id": "q.dados_ginasio",
  "confidence": 0.95,
  "reasoning": "User wants sports court lighting, saving answer and navigating to collect details",
  "messages": [
    {{"text": "Sim! Vendemos luminárias LED para quadras esportivas.", "delay_ms": 0}},
    {{"text": "Fazemos o projeto completo, cobertas ou descobertas.", "delay_ms": 1600}},
    {{"text": "Poderia me passar seu nome e email?", "delay_ms": 1900}}
  ]
}}

User: "meu email é test@example.com" (when node asks for name AND email)
Tool: PerformAction
Arguments: {{
  "actions": ["stay"],
  "clarification_reason": "partial_answer",
  "confidence": 0.9,
  "reasoning": "User provided email but not name, need to collect missing information",
  "messages": [
    {{"text": "Perfeito! Anotei seu email: test@example.com", "delay_ms": 0}},
    {{"text": "E qual é seu nome completo?", "delay_ms": 1500}}
  ]
}}

REMEMBER: ALWAYS include messages in your tool arguments!"""

        return instruction

    def _build_messaging_instructions(
        self,
        project_context: ProjectContext | None,
        is_completion: bool,
    ) -> str:
        """Build messaging instructions based on context."""
        instructions = []

        # Core messaging principles
        instructions.append(f"""
### Core Messaging Principles
- Generate {MIN_MESSAGES_PER_TURN}-{MAX_MESSAGES_PER_TURN} natural WhatsApp message bubbles
- First message always has delay_ms: {NO_DELAY_MS}
- Follow-up messages have delay_ms: {MAX_FOLLOWUP_DELAY_MS // 2}-{MAX_FOLLOWUP_DELAY_MS} (vary naturally)
- Keep each message concise (max {MAX_MESSAGE_LENGTH} characters)
- Sound conversational and warm
""")

        # Completion context
        if is_completion:
            instructions.append("""
### Completion Message
- Thank the user and indicate follow-up
- Example: "Perfeito! Vou verificar isso e te retorno em breve."
- Don't mention "human" explicitly
""")

        # Project context and business information
        if project_context:
            if project_context.project_description:
                instructions.append(f"""
### Business Information
{project_context.project_description}

Use this information to answer questions about what we do/sell and provide relevant context.
""")

            if project_context.communication_style:
                instructions.append(f"""
### Communication Style
{project_context.communication_style}

Apply this style naturally while maintaining conversational flow.
""")
        else:
            instructions.append("""
### Default Style (Warm Receptionist)
- Professional but friendly
- Natural Brazilian Portuguese
- Use contractions: 'tá', 'pra', 'né' (moderately)
- Like a receptionist you enjoy talking with
""")

        # Anti-patterns to avoid
        instructions.append("""
### AVOID These Patterns
- Don't repeat greetings after first interaction
- Don't start every message with "Claro!", "Entendi!"
- Don't repeat acknowledgments of same information
- Vary your responses - don't use same phrases repeatedly
- Don't be robotic or overly formal
""")

        return "\n".join(instructions)

    def _add_admin_instructions(self) -> str:
        """Add admin-specific instructions to the prompt."""
        return """
### ADMIN FLOW MODIFICATION
As an admin, you can modify the flow in real-time using the PerformAction tool with the "modify_flow" action.

**DETECTING ADMIN COMMANDS:**
Admin commands are meta-instructions about the flow itself, NOT answers to questions. Look for:
- "Change this question to..." / "Alterar esta pergunta para..."
- "Make this more/less..." / "Fazer isso mais/menos..."  
- "Add/remove a question..." / "Adicionar/remover uma pergunta..."
- "Break this into multiple questions..." / "Quebrar em múltiplas perguntas..."
- "Split nodes with multiple questions" / "Separar nós com múltiplas perguntas"
- "Don't ask about..." / "Não perguntar sobre..."
- Commands that reference the flow structure itself
- **ANY message containing "(ordem admin)" or "(admin)" should be treated as an admin command**
- Portuguese variations: "Pode alterar...", "Pode mudar...", "Pode dividir..."

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

**IMPORTANT: Confirmation Pattern**
ALWAYS confirm flow modifications before executing:
1. First response: Confirm what will be changed and ask for confirmation
   - Use actions=["stay"] (NOT "modify_flow" yet)
   - Explain clearly what changes will be made
   - Ask "Posso prosseguir com essa alteração?" or "Confirma essa modificação?"
2. After confirmation: Execute the modification
   - Use actions=["modify_flow", "stay"]
   - Include the flow_modification_instruction
   - Confirm the changes were requested

**Usage:**
When an admin requests flow changes:
- First time (no confirmation): Use PerformAction with actions=["stay"], explain changes, ask for confirmation
- After confirmation: Use PerformAction with:
  - `actions`: ["modify_flow", "stay"] to execute and stay on current node
  - `flow_modification_instruction`: Natural language instruction for the modification
  - `flow_modification_target` (optional): The ID of the specific node to modify
  - `flow_modification_type` (optional): Can be "prompt", "routing", "validation", or "general"
  - `messages`: Confirm the modification is being processed

**Examples:**

**Example 1: Initial request (needs confirmation)**
- Admin says: "Pode alterar os nos que tem multiplas perguntas pra varios nos com uma pergunta?"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Entendi! Você quer que eu separe todos os nós que têm múltiplas perguntas em nós individuais, uma pergunta por nó.", "delay_ms": 0},
      {"text": "Isso vai tornar o fluxo mais claro, perguntando uma coisa de cada vez.", "delay_ms": 1500},
      {"text": "Posso prosseguir com essa alteração?", "delay_ms": 1000}
    ]

**Example 2: After confirmation**
- Admin says: "Sim, pode fazer" or "Confirmo" or "Sim"
  → Use: PerformAction with actions=["modify_flow", "stay"], 
    flow_modification_instruction="Split all nodes that have multiple questions into separate nodes with one question each",
    messages=[{"text": "✅ Perfeito! Estou processando a separação dos nós com múltiplas perguntas...", "delay_ms": 0}]

**Example 3: Admin clarifies it's an order (with confirmation)**
- Admin says: "Nao, isso foi uma ordem como admin pra quebrar o flow em 3 perguntas ao inves de uma só"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Ah, entendi! É uma ordem administrativa para modificar o fluxo.", "delay_ms": 0},
      {"text": "Vou dividir a pergunta atual em 3 perguntas separadas sequenciais.", "delay_ms": 1500},
      {"text": "Confirma que posso fazer essa alteração agora?", "delay_ms": 1000}
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
      {"text": "[Repeat the current question from the flow]", "delay_ms": 1000}
    ]

**Example 6: Admin provides different instructions after initial request**
- Context: Admin asked to split nodes, you asked for confirmation
- Admin says: "Na verdade, só divida este nó atual em 2 partes"
  → Use: PerformAction with actions=["stay"], messages=[
      {"text": "Ah, entendi! Mudando o plano então.", "delay_ms": 0},
      {"text": "Vou dividir apenas o nó atual em 2 perguntas separadas.", "delay_ms": 1500},
      {"text": "Confirma essa alteração?", "delay_ms": 1000}
    ]
"""

    def _select_contextual_tools(
        self,
        context: FlowContext,
        pending_field: str | None,
        is_admin: bool = False,
    ) -> list[type]:
        """Select appropriate tools based on context."""
        # Use PerformAction as the main tool - it can handle multiple actions
        from ..tools import PerformAction, RequestHumanHandoff

        tools: list[type] = [
            PerformAction,  # This can do everything including flow modification for admins
            RequestHumanHandoff,  # For escalation
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
        from ..flow_types import PerformActionCall, RequestHumanHandoffCall

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
        elif tool_name == "RequestHumanHandoff":
            if "reason" not in tool_args:
                tool_args["reason"] = "explicit_request"
            if "context_summary" not in tool_args:
                tool_args["context_summary"] = "User requested human assistance"
            tool_call = RequestHumanHandoffCall(**tool_args)
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
