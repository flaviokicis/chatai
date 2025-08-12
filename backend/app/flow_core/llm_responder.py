"""LLM-based responder using tool calling for flow interactions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.llm import LLMClient

from app import dev_config

from .state import FlowContext
from .tool_schemas import (
    FLOW_TOOLS,
    ClarifyQuestion,
    RequestHumanHandoff,
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
            # Drop any assistant_message key returned by the model
            if isinstance(result, dict) and "assistant_message" in result:
                try:
                    del result["assistant_message"]
                except Exception:
                    result["assistant_message"] = ""
            if dev_config.debug:
                print(f"[DEBUG] LLM result: {result}")
        except Exception as e:
            if dev_config.debug:
                print(f"[DEBUG] LLM extraction failed: {e}")
            # Fallback response on error
            return FlowResponse(
                updates={},
                message="I'm having trouble understanding. Could you rephrase that?",
                tool_name=None,
                metadata={"error": str(e)},
            )

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

        # Detect conversation patterns
        patterns = self._detect_patterns(ctx, user_message)

        # Previously answered fields and most recent
        previously_answered = [k for k, v in ctx.answers.items() if v not in (None, "")]
        most_recent_answer_key = previously_answered[-1] if previously_answered else None
        most_recent_answer_val = (
            ctx.answers.get(most_recent_answer_key) if most_recent_answer_key else None
        )

        instruction = f"""You are helping a user through a conversational flow. Analyze their message and choose the correct tool.

Current Context:
- Question: {prompt}
- Field to fill: {pending_field or "none"}
- User's message: {user_message}
- Conversation style: {ctx.conversation_style or "adaptive"}
- Previous clarifications: {ctx.clarification_count}
- Previously answered fields: {previously_answered or "none"}
- Most recent previous answer: {most_recent_answer_key} = {most_recent_answer_val}

Collected Information:
{answers_summary}

Recent Conversation:
{history_text}

Detected Patterns:
- User seems to be: {", ".join(patterns) if patterns else "engaged normally"}
"""

        if allowed_values:
            values_str = ", ".join(allowed_values)
            instruction += f"\n\nIMPORTANT: If updating '{pending_field}', the value MUST be one of: {values_str}"

        instruction += """

        Choose the most appropriate tool based on the user's intent:
        - UpdateAnswersFlow: use when you can extract a concise answer for the CURRENT pending field.
          Guidance for extraction: ignore greetings and filler words; use the meaningful noun phrase or value the user provided. Keep the value short.
        - ClarifyQuestion: use if the user is asking about the meaning/purpose/options/format of the CURRENT question.
        - SkipQuestion: use if the user explicitly wants to skip (and skipping is allowed by policy).
        - RevisitQuestion: use when the user is correcting or changing any PREVIOUS answer (not the current question).
          Provide:
          * question_key: choose from previously answered fields (prefer the most recent) if the message suggests a correction.
          * revisit_value: extract the new value from the user's message when possible.
          If you cannot extract a clear new value, set revisit_value to null.

        CRITICAL DECISION RULES:
        - If the user's message includes correction signals like "meant", "actually", "sorry", "not ...", "change", "switch", "update" then DO NOT use UnknownAnswer; use RevisitQuestion instead.
        - Use RequestHumanHandoff only for explicit escalate requests or truly complex issues.
        - Use UnknownAnswer ONLY when the user explicitly indicates they do not know the answer to the CURRENT question or directly asks for clarification, and no correction is being made.
        - Examples of UnknownAnswer signals: "don't know", "not sure", "no idea", "?" or a direct question about the prompt.

        Output formatting:
        - Do NOT include any assistant_message field in tool arguments.
        - Only include fields defined for the tool (e.g., updates, validated, question_key, revisit_value, etc.).
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
            RequestHumanHandoff,
        ]

        # Add contextual tools
        if ctx.answers:  # User has answered something
            basic_tools.append(RevisitQuestion)

        if ctx.available_paths:  # Multi-path flow
            basic_tools.append(SelectFlowPath)

        if ctx.clarification_count > 2:  # User struggling
            basic_tools.append(SkipQuestion)

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

        # Extract common fields (assistant_message is not used by engine anymore)
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
                metadata={"validated": validated},
            )

        if tool_name == "ClarifyQuestion":
            ctx.clarification_count += 1
            return FlowResponse(
                updates={},
                message=message,
                tool_name=tool_name,
                metadata={
                    "clarification_type": result.get("clarification_type"),
                    "is_clarification": True,
                },
            )

        if tool_name == "SkipQuestion":
            skip_to = result.get("skip_to")
            return FlowResponse(
                updates={},
                message=message,
                tool_name=tool_name,
                navigation=skip_to,
                metadata={"skip_reason": result.get("reason")},
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
                message=message,
                tool_name=tool_name,
                navigation=target_node,
                metadata={"revisit_key": question_key, "revisit_value": revisit_value},
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
                message=message,
                tool_name=tool_name,
                confidence=path_confidence,
                metadata={"path": path, "reasoning": result.get("reasoning")},
            )

        if tool_name == "RequestHumanHandoff" or tool_name == "EscalateToHuman":
            return FlowResponse(
                updates={},
                message=message,
                tool_name=tool_name,
                escalate=True,
                escalate_reason=result.get("reason"),
                metadata={
                    "context": result.get("context", {}),
                    "urgency": result.get("urgency", "medium"),
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
                message=message,
                tool_name=tool_name,
                metadata={"field": field, "reason": reason},
            )

        if tool_name == "ProvideInformation":
            return FlowResponse(
                updates={},
                message=message,
                tool_name=tool_name,
                metadata={
                    "information_type": result.get("information_type"),
                    "related_to": result.get("related_to"),
                },
            )

        if tool_name == "ConfirmCompletion":
            ctx.is_complete = True
            return FlowResponse(
                updates={},
                message=message,
                tool_name=tool_name,
                metadata={
                    "summary": result.get("summary", {}),
                    "next_steps": result.get("next_steps", []),
                    "completion_type": result.get("completion_type", "success"),
                },
            )

        if tool_name == "NavigateFlow":
            return FlowResponse(
                updates={},
                message=message,
                tool_name=tool_name,
                navigation=result.get("target_node"),
                metadata={"navigation_type": result.get("navigation_type")},
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

    def _detect_patterns(self, ctx: FlowContext, user_message: str) -> list[str]:
        """Detect conversation patterns for better responses."""
        patterns = []

        # Check for frustration
        frustration_words = ["confused", "don't understand", "frustrated", "annoying", "stupid"]
        if any(word in user_message.lower() for word in frustration_words):
            patterns.append("frustrated")

        # Check for questions
        if "?" in user_message:
            patterns.append("asking questions")

        # Check for short responses
        if len(user_message.split()) <= 2:
            patterns.append("giving short answers")

        # Check for clarification pattern
        if ctx.clarification_count > 1:
            patterns.append("needing clarification")

        # Check for revisiting pattern
        change_words = ["change", "actually", "wait", "no", "wrong", "mistake"]
        if any(word in user_message.lower() for word in change_words):
            patterns.append("wanting to change something")

        return patterns

    def _find_node_for_key(self, ctx: FlowContext, question_key: str) -> str | None:
        """Find the node ID for a question key."""
        # This would need access to the compiled flow
        # For now, return None and let the engine handle it
        return None
