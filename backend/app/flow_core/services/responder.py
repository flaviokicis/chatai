"""Enhanced LLM responder service that handles both tool calling and message generation.

This service uses GPT-5 to intelligently process user messages, select appropriate tools,
and generate natural conversational responses in a single cohesive step.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

    from ..state import FlowContext

from langfuse import get_client

from app.core.prompt_logger import prompt_logger
from app.core.thought_tracer import DatabaseThoughtTracer

from ..constants import (
    DEFAULT_AGENT_TYPE,
    DEFAULT_ERROR_MESSAGE,
    DEFAULT_SESSION_ID,
    DEFAULT_USER_ID,
    MAX_FOLLOWUP_DELAY_MS,
    MAX_HISTORY_TURNS,
    MAX_MESSAGE_LENGTH,
    MAX_MESSAGES_PER_TURN,
    MAX_SCHEMA_VALIDATION_RETRIES,
    MAX_VALIDATION_ERRORS_TO_SHOW,
    MIN_MESSAGES_PER_TURN,
    MODEL_GPT5,
    NO_DELAY_MS,
    PROMPT_TYPE_GPT5_ENHANCED,
)
from ..tools import FLOW_TOOLS
from ..types import (
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
        thought_tracer: DatabaseThoughtTracer | None = None,
    ) -> None:
        """Initialize the enhanced responder.
        
        Args:
            llm: The LLM client (GPT-5) for processing
            thought_tracer: Optional thought tracer for debugging
        """
        self._llm = llm
        self._thought_tracer = thought_tracer
        self._langfuse = get_client()
        self._message_service = MessageGenerationService()
        self._tool_executor = ToolExecutionService()

    def respond(
        self,
        prompt: str,
        pending_field: str | None,
        context: FlowContext,
        user_message: str,
        allowed_values: list[str] | None = None,
        project_context: ProjectContext | None = None,
        is_completion: bool = False,
        available_edges: list[dict[str, Any]] | None = None,
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
        )

        # Select appropriate tools
        tools = self._select_contextual_tools(context, pending_field)

        # Start thought tracing if available
        thought_id = self._start_thought_trace(
            context=context,
            user_message=user_message,
            pending_field=pending_field,
            tools=tools,
        )

        try:
            # Call GPT-5 with enhanced schema and validation
            validated_response = self._call_gpt5(instruction, tools)

            # Process the validated response
            output = self._process_gpt5_response(
                response=validated_response,
                context=context,
                pending_field=pending_field,
                project_context=project_context,
            )

            # Complete thought tracing
            if thought_id and self._thought_tracer:
                self._complete_thought_trace(
                    thought_id=thought_id,
                    output=output,
                    response=validated_response,
                )

            return output

        except Exception as e:
            logger.exception("Error in enhanced responder")
            # Return fallback response
            return self._create_fallback_response(str(e))

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
    ) -> str:
        """Build comprehensive instruction for GPT-5."""
        # Get conversation history
        history = self._format_conversation_history(context)

        # Get current state
        state_summary = self._summarize_state(context)

        # Build messaging instructions
        messaging_instructions = self._build_messaging_instructions(
            project_context=project_context,
            is_completion=is_completion,
        )

        instruction = f"""You are a warm, friendly receptionist helping users through a conversation.
You must analyze the user's message, choose the appropriate tool, AND generate natural WhatsApp-style messages.

## CURRENT CONTEXT
Question: {prompt}
Pending field: {pending_field or "none"}
User message: {user_message}

## COLLECTED INFORMATION
{state_summary}

## CONVERSATION HISTORY
{history}

## CRITICAL RULES
1. YOU MUST GENERATE MESSAGES - Include messages in your content field as JSON array
2. Generate 1-3 warm, conversational WhatsApp messages
3. If user greets you (Ola, Oi, etc), ALWAYS greet back warmly before asking questions
4. Keep conversation flowing naturally - acknowledge, respond, then continue the flow

## MESSAGE FORMAT (PUT THIS IN YOUR CONTENT FIELD)
[
  {{"text": "First message - warm greeting or acknowledgment", "delay_ms": 0}},
  {{"text": "Second message - continue conversation naturally", "delay_ms": 1500}},
  {{"text": "Third message (if needed) - ask next question", "delay_ms": 1800}}
]

## TOOL SELECTION RULES

### UpdateAnswers
Use when you can extract an answer for the current pending field.
MANDATORY: The "updates" field must contain {{"{pending_field}": "extracted_value"}}
MANDATORY: Generate messages that acknowledge the answer AND continue to next question

Examples for field "{pending_field}":
- User: "campo de futebol" → updates: {{"{pending_field}": "campo de futebol"}}
  Messages: ["Ótimo! Uma quadra esportiva!", "Vou te ajudar com a iluminação ideal", "Qual o tamanho da quadra?"]

### StayOnThisNode
Use when response is unclear or user needs clarification
MANDATORY: Generate warm messages that clarify and re-ask the question naturally

### NavigateToNode
Use for navigation between nodes
MANDATORY: Generate messages that transition smoothly
{self._format_navigation_options(available_edges)}

### RequestHumanHandoff
Use when user needs human assistance
MANDATORY: Generate empathetic messages about transferring to specialist

### RestartConversation
Use ONLY when user explicitly says "restart", "start over"
MANDATORY: Generate fresh greeting messages

### ConfirmCompletion
Use when flow is complete
MANDATORY: Generate completion messages thanking user

{self._add_allowed_values_constraint(allowed_values, pending_field)}

## EXAMPLES OF GOOD RESPONSES

User: "Ola!"
Tool: StayOnThisNode (if at beginning) or current appropriate tool
Content: [
  {{"text": "Olá! Que bom falar com você! 😊", "delay_ms": 0}},
  {{"text": "Sou da equipe de atendimento", "delay_ms": 1200}},
  {{"text": "Como posso ajudar você hoje?", "delay_ms": 1500}}
]

User: "Eu tenho uma quadra"
Tool: UpdateAnswers
Content: [
  {{"text": "Que legal! Uma quadra esportiva! 🏐", "delay_ms": 0}},
  {{"text": "Temos soluções perfeitas para iluminação esportiva", "delay_ms": 1500}},
  {{"text": "Qual o tamanho aproximado da sua quadra?", "delay_ms": 1800}}
]

REMEMBER: ALWAYS include messages in your content field as a JSON array!"""

        return instruction

    def _build_messaging_instructions(
        self,
        project_context: ProjectContext | None,
        is_completion: bool,
    ) -> str:
        """Build messaging instructions based on context."""
        instructions = []

        # Core messaging principles
        instructions.append("""
### Core Messaging Principles
- Generate {MIN_MESSAGES_PER_TURN}-{MAX_MESSAGES_PER_TURN} natural WhatsApp message bubbles
- First message always has delay_ms: {NO_DELAY_MS}
- Follow-up messages have delay_ms: {MIN_FOLLOWUP_DELAY_MS}-{MAX_FOLLOWUP_DELAY_MS} (vary naturally)
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

        # Style instructions
        if project_context and project_context.communication_style:
            instructions.append(f"""
### Custom Communication Style
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

    def _select_contextual_tools(
        self,
        context: FlowContext,
        pending_field: str | None,
    ) -> list[type]:
        """Select appropriate tools based on context."""
        # Always include core tools
        tools: list[type] = [
            tool for tool in FLOW_TOOLS
            if tool.__name__ in [
                "UpdateAnswers",
                "StayOnThisNode",
                "RequestHumanHandoff",
                "ConfirmCompletion",
                "RestartConversation",
            ]
        ]

        # Add NavigateToNode if there are answers (can go back) or paths
        if context.answers or context.available_paths:
            from ..tools import NavigateToNode
            tools.append(NavigateToNode)

        return tools

    def _call_gpt5(
        self,
        instruction: str,
        tools: list[type],
        max_retries: int = MAX_SCHEMA_VALIDATION_RETRIES,
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
        # Create enhanced schema that includes both tool and messages
        enhanced_schema = {
            "type": "object",
            "properties": {
                "tool": {
                    "type": "object",
                    "oneOf": [
                        self._tool_to_schema(tool) for tool in tools
                    ]
                },
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                                            "properties": {
                        "text": {"type": "string", "maxLength": MAX_MESSAGE_LENGTH},
                        "delay_ms": {"type": "integer", "minimum": NO_DELAY_MS, "maximum": MAX_FOLLOWUP_DELAY_MS * 2}
                    },
                        "required": ["text", "delay_ms"]
                    },
                    "minItems": MIN_MESSAGES_PER_TURN,
                    "maxItems": MAX_MESSAGES_PER_TURN
                },
                "reasoning": {"type": "string", "maxLength": MAX_VALIDATION_ERRORS_TO_SHOW * 100}
            },
            "required": ["tool", "messages", "reasoning"]
        }

        last_error: GPT5SchemaError | None = None

        for attempt in range(max_retries + 1):
            try:
                # Call LLM with tools directly
                result = self._llm.extract(instruction, tools)

                # Log the interaction
                prompt_logger.log_prompt(
                    prompt_type=PROMPT_TYPE_GPT5_ENHANCED,
                    instruction=instruction,
                    input_text="",
                    response=json.dumps(result, ensure_ascii=False),
                    model=getattr(self._llm, "model_name", MODEL_GPT5),
                    metadata={
                        "tools": [t.__name__ for t in tools],
                        "attempt": attempt + 1,
                    }
                )

                # Use LangChain response directly - no unnecessary transformation
                return self._create_direct_gpt5_response(result, instruction)

            except GPT5SchemaError as e:
                last_error = e
                logger.warning(
                    f"GPT-5 schema validation failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
                )

                if attempt < max_retries:
                    # Add schema correction hint to instruction
                    instruction = self._add_schema_correction_hint(
                        instruction,
                        e.validation_errors,
                    )
                    continue

            except Exception as e:
                # Unexpected error
                logger.exception(f"Unexpected error calling GPT-5: {e}")
                raise GPT5SchemaError(
                    f"Unexpected error: {e}",
                    {},
                    [str(e)],
                )

        # All retries exhausted
        if last_error:
            raise last_error

        raise GPT5SchemaError(
            "Failed to get valid response from GPT-5",
            {},
            ["No valid response after retries"],
        )

    def _tool_to_schema(self, tool: type) -> dict[str, Any]:
        """Convert a tool class to JSON schema."""
        # This would use the tool's Pydantic schema
        # For now, returning a simplified version
        schema_func: Any = getattr(tool, "model_json_schema", lambda: {"properties": {}, "required": []})
        schema = schema_func()
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required = schema.get("required", []) if isinstance(schema, dict) else []
        
        result_properties = {"tool_name": {"const": tool.__name__}}
        if isinstance(properties, dict):
            result_properties.update(properties)
        
        result_required = ["tool_name"]
        if isinstance(required, list):
            result_required.extend(required)
        
        return {
            "type": "object",
            "properties": result_properties,
            "required": result_required
        }

    def _process_gpt5_response(
        self,
        response: GPT5Response,
        context: FlowContext,
        pending_field: str | None,
        project_context: ProjectContext | None,
    ) -> ResponderOutput:
        """Process the validated GPT-5 response.
        
        Args:
            response: Validated GPT5Response
            context: Current flow context
            pending_field: Currently pending field
            project_context: Project context for additional processing
            
        Returns:
            ResponderOutput with tool result and messages
        """
        # Get tool information
        tool_name = response.get_tool_name()
        tool_data = response.get_tool_data()

        # Add back confidence and reasoning to tool_data for executor
        tool_data["confidence"] = response.tool.confidence
        tool_data["reasoning"] = response.tool.reasoning

        # Execute the tool
        try:
            tool_result = self._tool_executor.execute_tool(
                tool_name=tool_name,
                tool_data=tool_data,
                context=context,
                pending_field=pending_field,
            )
        except Exception as e:
            logger.exception(f"Tool execution failed for {tool_name}: {e}")
            # Create error result
            tool_result = ToolExecutionResult(
                updates={},
                navigation=None,
                escalate=False,
                terminal=False,
                metadata={"error": str(e)},
            )

        # Messages are already validated by Pydantic
        messages = response.messages

        return ResponderOutput(
            tool_name=tool_name,
            tool_result=tool_result,
            messages=messages,
            confidence=response.tool.confidence,
            reasoning=response.reasoning,
        )

    def _add_schema_correction_hint(
        self,
        instruction: str,
        validation_errors: list[str],
    ) -> str:
        """Add schema correction hints to the instruction.
        
        Args:
            instruction: Original instruction
            validation_errors: List of validation errors
            
        Returns:
            Updated instruction with correction hints
        """
        error_summary = "\n".join(validation_errors[:MAX_VALIDATION_ERRORS_TO_SHOW])

        hint = f"""

## IMPORTANT: Schema Validation Error
Your previous response had validation errors:
{error_summary}

Please ensure:
1. Tool name matches exactly: UpdateAnswers, StayOnThisNode, NavigateToNode, etc.
2. All required fields are provided for the selected tool
3. Messages array has {MIN_MESSAGES_PER_TURN}-{MAX_MESSAGES_PER_TURN} items with 'text' and 'delay_ms' fields
4. First message must have delay_ms: {NO_DELAY_MS}
5. Text should be under {MAX_MESSAGE_LENGTH} characters per message
"""

        return instruction + hint

    def _format_navigation_options(self, available_edges: list[dict[str, Any]] | None) -> str:
        """Format available navigation options for the instruction."""
        if not available_edges:
            return ""

        edge_descriptions = []
        for edge in available_edges:
            target = edge.get("target_node_id", "unknown")
            desc = edge.get("description", f"Navigate to {target}")
            edge_descriptions.append(f"  - {desc}: use target_node_id='{target}'")

        if not edge_descriptions:
            return ""

        return "\n\nAvailable navigation options from current node:\n" + "\n".join(edge_descriptions)

    def _format_conversation_history(self, context: FlowContext) -> str:
        """Format conversation history for the prompt."""
        if not context.history:
            return "No previous conversation"

        # Take last MAX_HISTORY_TURNS turns
        recent = list(context.history)[-MAX_HISTORY_TURNS:]
        lines = []
        for turn in recent:
            role = turn.role.title() if hasattr(turn, "role") else "Unknown"
            content = turn.content if hasattr(turn, "content") else ""
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def _summarize_state(self, context: FlowContext) -> str:
        """Summarize the current state."""
        if not context.answers:
            return "No information collected yet"

        lines = []
        for key, value in context.answers.items():
            if value not in (None, ""):
                lines.append(f"- {key}: {value}")

        return "\n".join(lines) if lines else "No information collected yet"

    def _add_allowed_values_constraint(
        self,
        allowed_values: list[str] | None,
        pending_field: str | None,
    ) -> str:
        """Add constraint for allowed values if applicable."""
        if allowed_values and pending_field:
            return f"\nIMPORTANT: Field '{pending_field}' must be one of: {', '.join(allowed_values)}"
        return ""

    def _start_thought_trace(
        self,
        context: FlowContext,
        user_message: str,
        pending_field: str | None,
        tools: list[type],
    ) -> str | None:
        """Start thought tracing if available."""
        if not self._thought_tracer:
            return None


        tool_names = [t.__name__ for t in tools]
        current_state = {
            "answers": dict(context.answers),
            "pending_field": pending_field,
            "active_path": context.active_path,
        }

        # Extract session info
        session_id = getattr(context, "session_id", DEFAULT_SESSION_ID)
        user_id = getattr(context, "user_id", DEFAULT_USER_ID)
        tenant_id = getattr(context, "tenant_id", None)

        if tenant_id:
            return self._thought_tracer.start_thought(
                user_id=user_id,
                session_id=session_id,
                agent_type=DEFAULT_AGENT_TYPE,
                user_message=user_message,
                current_state=current_state,
                available_tools=tool_names,
                tenant_id=tenant_id,
                model_name=MODEL_GPT5,
                channel_id=getattr(context, "channel_id", None),
            )

        return None

    def _complete_thought_trace(
        self,
        thought_id: str,
        output: ResponderOutput,
        response: GPT5Response,
    ) -> None:
        """Complete thought tracing.
        
        Args:
            thought_id: ID of the thought trace
            output: The responder output
            response: The validated GPT-5 response
        """
        if not self._thought_tracer:
            return

        self._thought_tracer.complete_thought(
            thought_id=thought_id,
            reasoning=output.reasoning or "",
            selected_tool=output.tool_name or "none",
            tool_args=response.get_tool_data(),
            tool_result=str(output.tool_result.updates) if output.tool_result.updates else None,
            agent_response=output.messages[0]["text"] if output.messages else "",
            errors=None,
            extra_metadata={"message_count": len(output.messages)},
        )

    def _create_direct_gpt5_response(self, langchain_response: dict[str, Any], instruction: str) -> GPT5Response:
        """Create GPT5Response directly from LangChain without unnecessary transformations."""
        from ..types import GPT5Response, UpdateAnswersCall, StayOnThisNodeCall, NavigateToNodeCall, RequestHumanHandoffCall, ConfirmCompletionCall, RestartConversationCall
        
        tool_calls = langchain_response.get("tool_calls", [])
        content = langchain_response.get("content", "")
        
        # Extract the tool and its arguments
        if not tool_calls:
            # Default fallback
            tool_name = "StayOnThisNode"
            tool_args = {"reasoning": "No tool selected", "acknowledgment": "Entendi", "clarification_reason": "unclear_response", "confidence": 0.5}
        else:
            tool_call = tool_calls[0]
            tool_name = tool_call.get("name", "StayOnThisNode")
            tool_args = tool_call.get("arguments", {})
            
            # Ensure required fields
            if "reasoning" not in tool_args:
                tool_args["reasoning"] = f"Selected {tool_name}"
            if "confidence" not in tool_args:
                tool_args["confidence"] = 0.8
        
        # Create the appropriate tool model
        tool_args["tool_name"] = tool_name
        tool_model: UpdateAnswersCall | StayOnThisNodeCall | NavigateToNodeCall | RequestHumanHandoffCall | ConfirmCompletionCall | RestartConversationCall
        if tool_name == "UpdateAnswers":
            tool_model = UpdateAnswersCall(**tool_args)
        elif tool_name == "StayOnThisNode":
            if "acknowledgment" not in tool_args:
                tool_args["acknowledgment"] = "Entendi"
            if "clarification_reason" not in tool_args:
                tool_args["clarification_reason"] = "unclear_response"
            tool_model = StayOnThisNodeCall(**tool_args)
        elif tool_name == "NavigateToNode":
            tool_model = NavigateToNodeCall(**tool_args)
        elif tool_name == "RequestHumanHandoff":
            tool_model = RequestHumanHandoffCall(**tool_args)
        elif tool_name == "ConfirmCompletion":
            tool_model = ConfirmCompletionCall(**tool_args)
        elif tool_name == "RestartConversation":
            tool_model = RestartConversationCall(**tool_args)
        else:
            # Fallback to StayOnThisNode
            tool_model = StayOnThisNodeCall(
                tool_name="StayOnThisNode",
                reasoning=f"Unknown tool {tool_name}, staying on node",
                acknowledgment="Entendi",
                clarification_reason="unclear_response",
                confidence=0.3
            )
        
        # Generate messages based on context
        messages = self._extract_or_generate_messages(langchain_response, instruction, tool_name, tool_args)
        
        # Create the GPT5Response directly
        return GPT5Response(
            tool=tool_model,
            messages=messages,
            reasoning=str(tool_args.get("reasoning", "Processed user input"))
        )
    
    def _extract_or_generate_messages(self, 
                                      langchain_response: dict[str, Any], 
                                      instruction: str,
                                      tool_name: str,
                                      tool_args: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract messages from GPT-5 response - NEVER generate hardcoded messages."""
        # CRITICAL: GPT-5 MUST generate ALL messages - no hardcoded fallbacks!
        
        # Check if the LLM included messages in its content (structured format)
        content = langchain_response.get("content", "")
        
        # Try to parse messages from content if it looks like JSON
        if content and content.strip().startswith('['):
            try:
                parsed_messages = json.loads(content)
                if isinstance(parsed_messages, list) and all(
                    isinstance(m, dict) and "text" in m for m in parsed_messages
                ):
                    # Ensure delay_ms is present
                    for i, msg in enumerate(parsed_messages):
                        if "delay_ms" not in msg:
                            msg["delay_ms"] = NO_DELAY_MS if i == 0 else 1500
                    return parsed_messages[:MAX_MESSAGES_PER_TURN]
            except json.JSONDecodeError:
                pass
        
        # If GPT-5 didn't provide messages, we need to call it again with clearer instructions
        # For now, provide a minimal message that forces continuation
        logger.warning(f"GPT-5 didn't provide messages for tool {tool_name}. Need to improve prompt.")
        
        # Return minimal message that keeps conversation going
        # This should RARELY happen if prompt is good
        return [{"text": "...", "delay_ms": NO_DELAY_MS}]

    def _create_fallback_response(self, error: str) -> ResponderOutput:
        """Create a fallback response on error.
        
        Args:
            error: Error message
            
        Returns:
            Fallback ResponderOutput
        """
        fallback_message: WhatsAppMessage = {
            "text": DEFAULT_ERROR_MESSAGE,
            "delay_ms": NO_DELAY_MS
        }

        return ResponderOutput(
            tool_name=None,
            tool_result=ToolExecutionResult(
                updates={},
                navigation=None,
                escalate=False,
                terminal=False,
                metadata={"error": error},
            ),
            messages=[fallback_message],
            confidence=0.0,
            reasoning=f"Error occurred: {error}",
        )
