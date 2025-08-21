"""LLM-based responder using tool calling for flow interactions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.llm import LLMClient

from app import dev_config
from app.core.prompt_logger import prompt_logger

from .state import FlowContext
from .tool_schemas import (
    FLOW_TOOLS,
    ClarifyQuestion,
    PathCorrection,
    ProvideInformation,
    RequestHumanHandoff,
    RestartConversation,
    RevisitQuestion,
    SelectFlowPath,
    SkipQuestion,
    UnknownAnswer,
    UpdateAnswersFlow,
)


@dataclass(slots=True)
class FlowResponse:
    """Response from the LLM responder."""

    updates: dict[str, Any]
    message: str
    tool_name: str | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] | None = None
    escalate: bool = False
    escalate_reason: str | None = None
    navigation: str | None = None  # next node to navigate to


class LLMFlowResponder:
    """
    LLM-based responder that uses tool calling for intelligent flow interactions.

    This responder understands context and can:
    - Extract and validate answers
    - Handle clarifications naturally
    - Skip or revisit questions when appropriate
    - Select paths intelligently
    - Escalate when needed
    - Provide contextual help
    """

    def __init__(self, llm: LLMClient, use_all_tools: bool = False) -> None:  # type: ignore[name-defined]
        """
        Initialize the responder.

        Args:
            llm: The LLM client for tool calling
            use_all_tools: If True, use all available tools; if False, use a minimal set
        """
        self._llm = llm
        self._use_all_tools = use_all_tools

    def respond(
        self,
        prompt: str,
        pending_field: str | None,
        ctx: FlowContext,
        user_message: str,
        allowed_values: list[str] | None = None,
        *,
        extra_tools: list[type] | None = None,
        agent_custom_instructions: str | None = None,
    ) -> FlowResponse:
        """
        Generate a response using LLM tool calling.

        Args:
            prompt: The current question prompt
            pending_field: The field we're trying to fill
            ctx: The flow context with history and state
            user_message: The user's message
            allowed_values: Optional list of allowed values for validation

        Returns:
            FlowResponse with updates, message, and metadata
        """
        # Build context for the LLM
        instruction = self._build_instruction(
            prompt,
            pending_field,
            ctx,
            user_message,
            allowed_values,
            agent_custom_instructions=agent_custom_instructions,
        )

        # Select appropriate tools based on context
        tools = self._select_tools(ctx, pending_field)
        if extra_tools:
            tools = self._merge_tools(tools, extra_tools)

        # Debug logging
        if dev_config.debug:
            tool_names = [getattr(t, "__name__", str(t)) for t in tools]
            print(f"[DEBUG] Available tools: {tool_names}")
            print(f"[DEBUG] User message: '{user_message}'")
            print(f"[DEBUG] Pending field: {pending_field}")

        # Call LLM with tools
        try:
            result = self._llm.extract(instruction, tools)
            
            # Log the tool calling prompt and response
            prompt_logger.log_prompt(
                prompt_type="tool_calling",
                instruction=instruction,
                input_text=user_message or "",
                response=json.dumps(result, ensure_ascii=False) if result else "None",
                model=getattr(self._llm, 'model_name', 'unknown'),
                metadata={
                    "pending_field": pending_field,
                    "tools": [t.__name__ if hasattr(t, '__name__') else str(t) for t in tools],
                    "allowed_values": allowed_values
                }
            )
            
            if dev_config.debug:
                print(f"[DEBUG] LLM result: {result}")
        except Exception as e:
            # Log the error
            prompt_logger.log_prompt(
                prompt_type="tool_calling_error",
                instruction=instruction,
                input_text=user_message or "",
                response=f"ERROR: {e}",
                model=getattr(self._llm, 'model_name', 'unknown'),
                metadata={"error": str(e), "pending_field": pending_field}
            )
            
            if dev_config.debug:
                print(f"[DEBUG] LLM extraction failed: {e}")
            # Fallback response on error
            return FlowResponse(
                updates={},
                message="I'm having trouble understanding. Could you rephrase that?",
                tool_name=None,
                metadata={"error": str(e)},
            )

        # Ensure a short reasoning is always present for observability
        if isinstance(result, dict):
            if not result.get("reasoning"):
                try:
                    # Construct a minimal reasoning string
                    tool_name = str(result.get("__tool_name__", "")) or "(unknown)"
                    msg_snippet = (user_message or "").strip()[:80]
                    result["reasoning"] = (
                        f"Chose {tool_name} based on user message: '{msg_snippet}'"
                    )
                except Exception:
                    pass

        # Process the tool response
        return self._process_tool_response(result, pending_field, ctx)

    def _build_instruction(
        self,
        prompt: str,
        pending_field: str | None,
        ctx: FlowContext,
        user_message: str,
        allowed_values: list[str] | None,
        *,
        agent_custom_instructions: str | None = None,
    ) -> str:
        """Build the instruction for the LLM."""
        # Get conversation context
        history = ctx.get_recent_history(5)
        history_text = (
            "\n".join(f"{h['role']}: {h['content']}" for h in history)
            if history
            else "No previous conversation"
        )

        # Build current state summary
        answers_summary = self._summarize_answers(ctx.answers)

        # Let LLM infer user patterns from context (no hardcoded detection)

        # Previously answered fields and most recent
        previously_answered = [k for k, v in ctx.answers.items() if v not in (None, "")]
        most_recent_answer_key = previously_answered[-1] if previously_answered else None
        most_recent_answer_val = (
            ctx.answers.get(most_recent_answer_key) if most_recent_answer_key else None
        )

        # Add flow structure awareness if we have path information
        flow_structure_info = ""
        if ctx.available_paths:
            flow_structure_info = f"\n\nAvailable flow paths: {', '.join(ctx.available_paths)}"
        if ctx.active_path:
            flow_structure_info += f"\nCurrently on path: {ctx.active_path}"

        # Check if we recently made a path selection
        selected_path = ctx.answers.get("selected_path")
        if selected_path:
            flow_structure_info += f"\nPreviously selected path: {selected_path}"

        instruction = f"""You are helping a user through a conversational flow. Analyze their message and choose the correct tool.

Current Context:
- Question: {prompt}
- Field to fill: {pending_field or "none"}
- User's message: {user_message}
- Conversation style: {ctx.conversation_style or "adaptive"}
- Previous clarifications: {ctx.clarification_count}
- Previously answered fields: {previously_answered or "none"}
- Most recent previous answer: {most_recent_answer_key} = {most_recent_answer_val}{flow_structure_info}

Collected Information:
{answers_summary}

Recent Conversation:
{history_text}

"""

        if allowed_values:
            values_str = ", ".join(allowed_values)
            instruction += f"\n\nIMPORTANT: If updating '{pending_field}', the value MUST be one of: {values_str}"

        instruction += """

        Choose the most appropriate tool based on the user's intent:
        - UpdateAnswersFlow: use when you can extract an answer for the CURRENT pending field.
          Guidance for extraction: ignore greetings and filler words; use the meaningful noun phrase or value the user provided.
          CRITICAL: Preserve qualifiers, comparators and units from the user's wording.
          - Do NOT remove words like: "até"/"up to", "no máximo"/"at most", "pelo menos"/"at least",
            "mais de"/"more than", "menos de"/"less than", "cerca de"/"about", "aprox."/"approximately",
            ranges like "entre X e Y", tildes "~", and currency/measurement units (ex.: "reais", "R$", "m", "lux").
          - Prefer capturing the exact span the user said (e.g., "até 1000 reais") over a normalized value ("1000 reais").
          - When in doubt, include more of the original phrase to preserve meaning rather than shortening it.
        - ProvideInformation: use for meta-level acknowledgments or brief information that does NOT change state
          (e.g., reassuring the user that their case is fine, answering "is that a problem?", or offering a quick tip).
        - ClarifyQuestion: use if the user is asking about the meaning/purpose/options/format of the CURRENT question.
          The system will generate a detailed explanation with examples to help the user understand.
        - SkipQuestion: use if the user explicitly wants to skip (and skipping is allowed by policy).
        - RevisitQuestion: use when the user is correcting or changing any PREVIOUS answer (not the current question).
          Provide:
          * question_key: choose from previously answered fields (prefer the most recent) if the message suggests a correction.
          * revisit_value: extract the new value from the user's message when possible.
          If you cannot extract a clear new value, set revisit_value to null.
          IMPORTANT: If the user is correcting a PATH SELECTION (e.g., "actually it's football" after choosing "outros"),
          use PathCorrection tool instead (if available) or SelectFlowPath with the corrected path.
        - PathCorrection: use when the user is correcting a path selection they made earlier.
          Common signals: "actually it's...", "I meant...", "no, it's...", "sorry, it's...", "na verdade é...", "quer dizer...".
          IMPORTANT: For corrected_path, choose EXACTLY from the available flow paths list above. 
          Map the user's correction to the correct path name (e.g., "quadra de tenis" → "quadra/tênis").
        - RequestHumanHandoff: use when the user is genuinely stuck, frustrated, or needs complex help.
          Watch for signs of confusion, repeated clarification requests on the same topic, expressions of frustration,
          or when the user's needs are too complex/specific for the current flow.
        - RestartConversation: STRICTLY use only if the user explicitly and unequivocally requests to "restart from scratch", "start over from the beginning", or equivalent explicit phrases. Do NOT use for vague restart-like language.

        CRITICAL DECISION RULES:
        - If the user's message includes correction signals like "meant", "actually", "sorry", "not ...", "change", "switch", "update":
          * For path corrections (e.g., "actually it's a football field", "na verdade é campo de futebol"):
            - First choice: use PathCorrection if available (it will normalize the path)
            - Second choice: use SelectFlowPath with the corrected path
            - Last resort: use RevisitQuestion with question_key="selected_path" and the corrected value
          * For answer corrections: use RevisitQuestion
          * DO NOT use UnknownAnswer for any corrections.
        - If the user's message expresses that their case doesn't match offered examples/options, but they are NOT asking about the current question's meaning, prefer ProvideInformation with a short positive acknowledgment.
        - Use RequestHumanHandoff when you detect user frustration, confusion after multiple clarifications, or complex requirements that don't fit the standard flow.
          Signs to watch for: repeated questions, expressions of confusion/frustration, very specific technical needs, or asking to speak to someone else.
        - Use UnknownAnswer ONLY when the user explicitly indicates they do not know the answer to the CURRENT question, and no correction is being made.
        - ClarifyQuestion should be used liberally when users ask for clarification - it will generate helpful explanations with examples.
        - Use RestartConversation ONLY if the message contains explicit phrases like: "restart from scratch", "start over from scratch", "start over", "reset everything", "let's begin again from the start".
          Ignore weak signals like "restart", "again", or "let's try that" unless accompanied by an explicit from-scratch request.

        Output formatting:
        - Do NOT include any assistant_message field. The assistant-facing text will be generated by a separate rewrite model.
        - Only include fields defined for the tool (e.g., updates, validated, question_key, revisit_value, etc.).
        - Always include a 'reasoning' field (one short sentence) explaining why this tool is the best choice for the user's message and context.
        """

        # Prepend any agent-provided custom instructions at the very top
        if agent_custom_instructions:
            header = agent_custom_instructions.strip()
            if header:
                instruction = f"{header}\n\n{instruction}"

        return instruction

    def _select_tools(self, ctx: FlowContext, pending_field: str | None) -> list[type]:
        """Select appropriate tools based on context."""
        if self._use_all_tools:
            return FLOW_TOOLS

        # Basic tool set for most interactions
        basic_tools = [
            UpdateAnswersFlow,
            UnknownAnswer,
            ClarifyQuestion,
            ProvideInformation,
            RequestHumanHandoff,
        ]

        # Add contextual tools
        if ctx.answers:  # User has answered something
            basic_tools.append(RevisitQuestion)
            # Add PathCorrection if we have a selected path
            if ctx.answers.get("selected_path") or ctx.active_path:
                basic_tools.append(PathCorrection)

        if ctx.available_paths:  # Multi-path flow
            basic_tools.append(SelectFlowPath)

        if ctx.clarification_count > 2:  # User struggling
            basic_tools.append(SkipQuestion)

        # The restart tool is always available but MUST be explicitly triggered by the LLM per strict rules
        basic_tools.append(RestartConversation)

        return basic_tools

    def _merge_tools(self, base: list[type], extra: list[type]) -> list[type]:
        """Merge tool class lists while preserving order and removing duplicates."""
        merged: list[type] = []
        seen: set[type] = set()
        for tool in list(base) + list(extra):
            if tool not in seen:
                seen.add(tool)
                merged.append(tool)
        return merged

    def _process_tool_response(
        self,
        result: dict[str, Any],
        pending_field: str | None,
        ctx: FlowContext,
    ) -> FlowResponse:
        """Process the tool response from the LLM."""
        tool_name = result.get("__tool_name__", "")

        # Ignore any assistant_message from the tool LLM; generation happens in the rewrite stage
        message = ""
        confidence = result.get("confidence", 1.0)

        # Handle each tool type
        if tool_name == "UpdateAnswersFlow" or tool_name == "UpdateAnswers":
            updates = self._normalize_updates(result.get("updates", {}), pending_field)
            validated = result.get("validated", True)

            # Apply validation if needed
            if pending_field and pending_field in updates and not validated:
                # Mark for validation in the engine
                ctx.get_node_state(ctx.current_node_id or "").metadata["needs_validation"] = True

            return FlowResponse(
                updates=updates,
                message=message,
                tool_name=tool_name,
                confidence=confidence,
                metadata={"validated": validated, "reasoning": result.get("reasoning")},
            )

        if tool_name == "ClarifyQuestion":
            ctx.clarification_count += 1
            return FlowResponse(
                updates={},
                message="",
                tool_name=tool_name,
                metadata={
                    "clarification_type": result.get("clarification_type"),
                    "is_clarification": True,
                    "reasoning": result.get("reasoning"),
                },
            )

        if tool_name == "SkipQuestion":
            skip_to = result.get("skip_to")
            return FlowResponse(
                updates={},
                message="",
                tool_name=tool_name,
                navigation=skip_to,
                metadata={
                    "skip_reason": result.get("reason"),
                    "reasoning": result.get("reasoning"),
                },
            )

        if tool_name == "RevisitQuestion":
            question_key = result.get("question_key")
            revisit_value = result.get("revisit_value")

            # If we have both key and value, we can update immediately
            updates = {}
            if question_key and revisit_value:
                updates[question_key] = revisit_value

            # Find the node for this question
            target_node = self._find_node_for_key(ctx, question_key)

            return FlowResponse(
                updates=updates,
                message="",
                tool_name=tool_name,
                navigation=target_node,
                metadata={
                    "revisit_key": question_key,
                    "revisit_value": revisit_value,
                    "reasoning": result.get("reasoning"),
                },
            )

        if tool_name == "SelectFlowPath" or tool_name == "SelectPath":
            path = result.get("path")
            path_confidence = result.get("confidence", 0.5)

            # Update path confidence in context
            if path:
                ctx.path_confidence[path] = max(
                    ctx.path_confidence.get(path, 0),
                    path_confidence,
                )

            return FlowResponse(
                updates={"selected_path": path} if path else {},
                message="",
                tool_name=tool_name,
                confidence=path_confidence,
                metadata={"path": path, "reasoning": result.get("reasoning")},
            )

        if tool_name == "RequestHumanHandoff" or tool_name == "EscalateToHuman":
            return FlowResponse(
                updates={},
                message="",
                tool_name=tool_name,
                escalate=True,
                escalate_reason=result.get("reason"),
                metadata={
                    "context": result.get("context", {}),
                    "urgency": result.get("urgency", "medium"),
                    "reasoning": result.get("reasoning"),
                },
            )

        if tool_name == "UnknownAnswer":
            field = result.get("field") or pending_field
            reason = result.get("reason", "unknown")

            # Mark field as attempted but unknown
            if field:
                node_state = ctx.get_node_state(ctx.current_node_id or "")
                node_state.metadata[f"{field}_unknown"] = reason

            return FlowResponse(
                updates={},
                message="",
                tool_name=tool_name,
                metadata={
                    "field": field,
                    "reason": reason,
                    "reasoning": result.get("reasoning"),
                },
            )

        if tool_name == "ProvideInformation":
            return FlowResponse(
                updates={},
                message="",
                tool_name=tool_name,
                metadata={
                    "information_type": result.get("information_type"),
                    "related_to": result.get("related_to"),
                    "reasoning": result.get("reasoning"),
                },
            )

        if tool_name == "ConfirmCompletion":
            ctx.is_complete = True
            return FlowResponse(
                updates={},
                message="",
                tool_name=tool_name,
                metadata={
                    "summary": result.get("summary", {}),
                    "next_steps": result.get("next_steps", []),
                    "completion_type": result.get("completion_type", "success"),
                    "reasoning": result.get("reasoning"),
                },
            )

        if tool_name == "NavigateFlow":
            return FlowResponse(
                updates={},
                message="",
                tool_name=tool_name,
                navigation=result.get("target_node"),
                metadata={
                    "navigation_type": result.get("navigation_type"),
                    "reasoning": result.get("reasoning"),
                },
            )

        if tool_name == "PathCorrection":
            corrected_path = result.get("corrected_path")
            original_path = result.get("original_path")

            # LLM should have already chosen from available paths, no normalization needed
            return FlowResponse(
                updates={"selected_path": corrected_path} if corrected_path else {},
                message="",
                tool_name=tool_name,
                confidence=result.get("confidence", 0.8),
                metadata={
                    "corrected_path": corrected_path,
                    "normalized_path": corrected_path,  # Same as corrected_path now
                    "original_path": original_path,
                    "reasoning": result.get("reasoning"),
                },
            )

        if tool_name == "RestartConversation":
            return FlowResponse(
                updates={},
                message="",
                tool_name=tool_name,
                metadata={
                    "reason": result.get("reason", "explicit_user_request"),
                    "reasoning": result.get("reasoning"),
                },
            )

        # Unknown tool or no tool selected
        # Try to extract updates if present (backward compatibility)
        updates = self._normalize_updates(result.get("updates", {}), pending_field)
        if updates and pending_field and pending_field in updates:
            return FlowResponse(
                updates=updates,
                message=message or "Got it, I've recorded your answer.",
                tool_name="UpdateAnswersFlow",
            )

        return FlowResponse(
            updates={},
            message=message or "I understand. Let me help you with that.",
            tool_name=None,
        )

    def _normalize_updates(self, updates_raw: Any, pending_field: str | None) -> dict[str, Any]:
        """Normalize the updates payload into a dict.

        Accepts dict, JSON-encoded string, or plain string (mapped to pending_field).
        """
        if isinstance(updates_raw, dict):
            return updates_raw

        # Try JSON decode if it's a string
        if isinstance(updates_raw, str):
            text = updates_raw.strip()
            if text:
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    # Not JSON, fall through to mapping to pending_field
                    pass
            if pending_field:
                return {pending_field: updates_raw}
            return {}

        # Unsupported type; nothing to update
        return {}

    def _summarize_answers(self, answers: dict[str, Any]) -> str:
        """Create a summary of collected answers."""
        if not answers:
            return "No information collected yet"

        lines = []
        for key, value in answers.items():
            if value not in (None, ""):
                lines.append(f"- {key}: {value}")

        return "\n".join(lines) if lines else "No information collected yet"

    # Removed hardcoded pattern detection - LLM can infer user state from context

    def _find_node_for_key(self, ctx: FlowContext, question_key: str) -> str | None:
        """Find the node ID for a question key."""
        # This would need access to the compiled flow
        # For now, return None and let the engine handle it
        return None

    # Removed _normalize_path_name - PathCorrection tool now directly returns normalized paths
