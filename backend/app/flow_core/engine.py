"""LLM-oriented flow engine for flexible, intelligent conversations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.core.llm import LLMClient

    from .compiler import CompiledFlow

from .ir import DecisionNode, QuestionNode, TerminalNode
from .state import FlowContext, NodeStatus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EngineResponse:
    """Response from the engine after processing."""

    kind: Literal["prompt", "terminal", "escalate"]
    message: str | None
    node_id: str | None
    metadata: dict[str, Any] | None = None
    suggested_actions: list[str] | None = None


class LLMFlowEngine:
    """
    LLM-oriented flow engine that provides flexibility within constraints.

    Key principles:
    1. The flow defines the script/structure, not rigid rules
    2. LLMs can skip, revisit, or clarify as needed for natural conversation
    3. Guards become suggestions, not hard blocks
    4. Context-aware decisions based on conversation history
    """

    def __init__(
        self,
        compiled: CompiledFlow,  # type: ignore[name-defined]
        llm: LLMClient | None = None,
        *,
        strict_mode: bool = False,
    ) -> None:
        """
        Initialize the engine.

        Args:
            compiled: The compiled flow to execute
            llm: Optional LLM client for intelligent decisions
            strict_mode: If True, enforce traditional state machine behavior
        """
        self._flow = compiled
        self._llm = llm
        self._strict_mode = strict_mode

    def initialize_context(self, existing_context: FlowContext | None = None) -> FlowContext:
        """Initialize or restore flow context."""
        if existing_context:
            return existing_context

        ctx = FlowContext(flow_id=self._flow.id)

        # Set entry point
        ctx.current_node_id = self._flow.entry

        # Identify available paths if any
        ctx.available_paths = self._identify_paths()

        return ctx

    def process(
        self,
        ctx: FlowContext,
        user_message: str | None = None,
        event: dict[str, Any] | None = None,
    ) -> EngineResponse:
        """
        Process a turn in the conversation.

        This is the main entry point that orchestrates:
        1. Understanding user intent
        2. Updating context
        3. Deciding next action
        4. Generating response
        """
        # Add user message to history if provided
        if user_message:
            ctx.add_turn("user", user_message, ctx.current_node_id)

        # Get current node
        node = self._get_current_node(ctx)
        if not node:
            return self._handle_no_node(ctx)

        # Process based on node type
        if isinstance(node, QuestionNode):
            return self._process_question_node(ctx, node, user_message, event)
        if isinstance(node, DecisionNode):
            return self._process_decision_node(ctx, node, event)
        if isinstance(node, TerminalNode):
            return self._process_terminal_node(ctx, node)
        logger.warning(f"Unknown node type: {type(node).__name__}")
        return EngineResponse(
            kind="escalate",
            message="I encountered an unexpected situation. Let me get someone to help.",
            node_id=node.id if node else None,
        )

    def _process_question_node(
        self,
        ctx: FlowContext,
        node: QuestionNode,
        user_message: str | None,
        event: dict[str, Any] | None,
    ) -> EngineResponse:
        """Process a question node with LLM awareness."""
        ctx.mark_node_visited(node.id)
        ctx.pending_field = node.key

        # If we have an event with an answer, process it
        if event and "answer" in event:
            # Validate if validator exists
            answer = event["answer"]
            if node.validator and not self._validate_answer(node, answer, ctx):
                ctx.clarification_count += 1
                return EngineResponse(
                    kind="prompt",
                    message=self._generate_validation_prompt(node, answer, ctx),
                    node_id=node.id,
                    metadata={"validation_failed": True},
                )

            # Store answer and mark complete
            ctx.answers[node.key] = answer
            ctx.get_node_state(node.id).status = NodeStatus.COMPLETED

            # Advance to next node
            return self._advance_from_node(ctx, node, event)

        # If we have a tool-driven event (without an explicit answer), handle accordingly
        if event and isinstance(event, dict) and event.get("tool_name"):
            handled = self._handle_tool_event(ctx, node, event)
            if handled:
                return handled

        # Check if user is asking for clarification
        if user_message and self._is_clarification_request(user_message, ctx):
            ctx.clarification_count += 1
            return EngineResponse(
                kind="prompt",
                message=self._generate_clarification(node, user_message, ctx),
                node_id=node.id,
                metadata={"is_clarification": True},
            )

        # Generate the prompt (potentially contextual)
        prompt = self._generate_contextual_prompt(node, ctx)
        # Add light cohesion: if we just captured a value this turn, prepend a short acknowledgement
        ack_prefix = None
        if user_message and ctx.turn_count > 0 and ctx.pending_field:
            # Only acknowledge when user replied while this question was pending
            ack_prefix = None  # kept for future expansion; keep output stable for now

        return EngineResponse(
            kind="prompt",
            message=prompt if not ack_prefix else f"{ack_prefix} {prompt}",
            node_id=node.id,
            suggested_actions=self._suggest_actions(node, ctx),
        )

    def _handle_tool_event(
        self, ctx: FlowContext, node: QuestionNode, event: dict[str, Any]
    ) -> EngineResponse | None:  # type: ignore[name-defined]
        """Handle non-answer tool events during a question node.

        Supported tools:
        - UnknownAnswer: mark node as skipped and advance
        - SkipQuestion: mark skipped and advance or jump if skip_to provided
        - RevisitQuestion: jump to target node
        - RequestHumanHandoff: escalate
        - ProvideInformation: stay on node (show clarification/ack if any)
        - ConfirmCompletion: mark complete
        - NavigateFlow: jump to target node
        """
        tool_name = str(event.get("tool_name") or "")
        ack = str(event.get("ack_message") or "")

        def _with_ack(res: EngineResponse) -> EngineResponse:
            if not ack:
                return res
            if res.kind == "prompt":
                if res.message:
                    res.message = f"{ack} {res.message}"
                else:
                    res.message = ack
            return res

        if tool_name == "UnknownAnswer":
            # Mark as skipped and advance
            ctx.get_node_state(node.id).status = NodeStatus.SKIPPED
            return self._advance_from_node(ctx, node, event)

        if tool_name == "SkipQuestion":
            ctx.get_node_state(node.id).status = NodeStatus.SKIPPED
            target = event.get("skip_to") or event.get("navigation")
            if isinstance(target, str) and target:
                ctx.current_node_id = target
                return _with_ack(self.process(ctx, None, None))
            return self._advance_from_node(ctx, node, event)

        if tool_name == "RevisitQuestion":
            target = event.get("target_node") or event.get("navigation")
            if isinstance(target, str) and target:
                ctx.current_node_id = target
                return _with_ack(self.process(ctx, None, None))
            # If no target provided, remain on current node
            return EngineResponse(
                kind="prompt",
                message=ack or self._generate_contextual_prompt(node, ctx),
                node_id=node.id,
            )

        if tool_name == "RequestHumanHandoff":
            return EngineResponse(
                kind="escalate",
                message=ack or "Transferring you to a human for further assistance.",
                node_id=node.id,
                metadata={"reason": event.get("reason", "unspecified")},
            )

        if tool_name == "ProvideInformation":
            # Stay on the same node; provide informational ack if any
            return EngineResponse(
                kind="prompt",
                message=ack or self._generate_contextual_prompt(node, ctx),
                node_id=node.id,
            )

        if tool_name == "ConfirmCompletion":
            ctx.is_complete = True
            return EngineResponse(
                kind="terminal",
                message=ack or "All questions have been answered. Thank you!",
                node_id=node.id,
            )

        if tool_name == "NavigateFlow":
            target = event.get("target_node") or event.get("navigation")
            if isinstance(target, str) and target:
                ctx.current_node_id = target
                return _with_ack(self.process(ctx, None, None))
            return EngineResponse(
                kind="prompt",
                message=ack or self._generate_contextual_prompt(node, ctx),
                node_id=node.id,
            )

        # Unknown tool; let default prompt logic run
        return None

    def _process_decision_node(
        self,
        ctx: FlowContext,
        node: DecisionNode,
        event: dict[str, Any] | None,
    ) -> EngineResponse:
        """Process a decision node with LLM-aware edge selection."""
        ctx.mark_node_visited(node.id)

        # Get edges from this node
        edges = self._flow.edges_from.get(node.id, [])
        if not edges:
            return self._handle_dead_end(ctx, node)

        # In strict mode, use traditional guard evaluation
        if self._strict_mode:
            for edge in edges:
                if self._evaluate_guard(edge, ctx, event):
                    ctx.current_node_id = edge.target
                    return self.process(ctx, None, None)
            return self._handle_no_valid_transition(ctx, node)

        # In LLM mode, use intelligent edge selection
        selected_edge = self._select_edge_intelligently(edges, ctx, event)
        if selected_edge:
            ctx.current_node_id = selected_edge.target
            return self.process(ctx, None, None)

        return self._handle_no_valid_transition(ctx, node)

    def _process_terminal_node(
        self,
        ctx: FlowContext,
        node: TerminalNode,
    ) -> EngineResponse:
        """Process a terminal node."""
        ctx.mark_node_visited(node.id, NodeStatus.COMPLETED)
        ctx.is_complete = True

        return EngineResponse(
            kind="terminal",
            message=node.reason or "Conversation complete",
            node_id=node.id,
            metadata={"final_answers": ctx.answers},
        )

    def _advance_from_node(
        self,
        ctx: FlowContext,
        node: Any,
        event: dict[str, Any] | None,
    ) -> EngineResponse:
        """Advance from current node to next."""
        edges = self._flow.edges_from.get(node.id, [])

        def _with_ack(res: EngineResponse) -> EngineResponse:
            # If caller provided an ack message (e.g., from responder), merge it for cohesion
            ack = (event or {}).get("ack_message") if isinstance(event, dict) else None
            if ack and res.kind == "prompt":
                ack_text = str(ack).strip()
                if ack_text:
                    if res.message:
                        res.message = f"{ack_text} {res.message}"
                    else:
                        res.message = ack_text
            return res

        if not edges:
            # No outgoing edges, find next question or complete
            return _with_ack(self._find_next_question(ctx))

        # Evaluate edges
        for edge in edges:
            if self._evaluate_guard(edge, ctx, event):
                ctx.current_node_id = edge.target
                return _with_ack(self.process(ctx, None, None))

        # No valid edge, stay on current node
        return _with_ack(self.process(ctx, None, None))

    def _find_next_question(self, ctx: FlowContext) -> EngineResponse:
        """Find the next unanswered question intelligently."""
        if not self._llm and not self._strict_mode:
            # Fallback to simple priority-based selection
            return self._find_next_question_simple(ctx)

        # Use LLM to determine best next question based on context
        unanswered = self._get_unanswered_questions(ctx)
        if not unanswered:
            ctx.is_complete = True
            return EngineResponse(
                kind="terminal",
                message="All questions have been answered. Thank you!",
                node_id=ctx.current_node_id,
            )

        # In strict mode, pick by priority
        if self._strict_mode:
            next_q = min(unanswered, key=lambda q: q.get("priority", 999))
        else:
            # Let LLM pick based on conversation flow
            next_q = self._select_next_question_intelligently(unanswered, ctx)

        if next_q:
            ctx.current_node_id = next_q["id"]
            return self.process(ctx, None, None)

        return EngineResponse(
            kind="terminal",
            message="I've collected all the information I need. Thank you!",
            node_id=ctx.current_node_id,
        )

    def _generate_contextual_prompt(self, node: QuestionNode, ctx: FlowContext) -> str:
        """Generate a context-aware prompt."""
        base_prompt = node.prompt

        if not self._llm or self._strict_mode:
            return base_prompt

        # Check if this is a revisit
        node_state = ctx.get_node_state(node.id)
        if node_state.visits > 1:
            return self._generate_revisit_prompt(node, ctx)

        # Check conversation style and adapt
        if ctx.conversation_style == "casual":
            return self._make_casual(base_prompt, ctx)
        if ctx.conversation_style == "technical":
            return self._make_technical(base_prompt, ctx)

        # Add context if relevant
        if ctx.turn_count > 0 and self._should_add_context(node, ctx):
            return self._add_conversational_context(base_prompt, ctx)

        return base_prompt

    def _is_clarification_request(self, message: str, ctx: FlowContext) -> bool:
        """Detect if user is asking for clarification."""
        if not self._llm:
            # Simple heuristic
            clarification_keywords = [
                "what do you mean",
                "can you explain",
                "i don't understand",
                "what does that mean",
                "why do you need",
                "what for",
                "?",
            ]
            message_lower = message.lower()
            return any(keyword in message_lower for keyword in clarification_keywords)

        # Use LLM for better detection
        try:
            instruction = (
                "Is the user asking for clarification about the current question? "
                "Answer with just 'yes' or 'no'."
            )
            response = self._llm.rewrite(instruction, message)
            return response.lower().strip().startswith("y")
        except Exception:
            return False

    def _generate_clarification(
        self, node: QuestionNode, user_message: str, ctx: FlowContext
    ) -> str:
        """Generate a clarification for the current question."""
        if not self._llm:
            # Simple template-based clarification
            return f"Let me clarify: {node.prompt}\n\nThis helps us understand your needs better."

        # Use LLM for contextual clarification
        try:
            instruction = (
                f"The user asked: '{user_message}' about the question: '{node.prompt}'. "
                f"Provide a helpful clarification that explains why we need this information. "
                f"Keep it concise and friendly."
            )
            context_info = f"We're discussing: {ctx.user_intent or 'your requirements'}"
            return self._llm.rewrite(instruction, context_info)
        except Exception:
            return f"Let me clarify: {node.prompt}"

    def _validate_answer(self, node: QuestionNode, answer: Any, ctx: FlowContext) -> bool:
        """Validate an answer using the node's validator."""
        if not node.validator:
            return True

        # TODO: Implement validator execution
        # For now, return True
        return True

    def _generate_validation_prompt(self, node: QuestionNode, answer: Any, ctx: FlowContext) -> str:
        """Generate a prompt for validation failure."""
        if not self._llm:
            return f"I couldn't understand '{answer}'. {node.prompt}"

        try:
            instruction = (
                f"The user provided '{answer}' for '{node.prompt}' but it's not valid. "
                f"Generate a friendly message asking them to provide a valid answer. "
                f"Be specific about what's expected."
            )
            return self._llm.rewrite(instruction, "")
        except Exception:
            return f"I couldn't process '{answer}'. Could you please try again? {node.prompt}"

    def _evaluate_guard(self, edge: Any, ctx: FlowContext, event: dict[str, Any] | None) -> bool:
        """Evaluate a guard function."""
        if not edge.guard_fn:
            return True

        guard_ctx = {
            "answers": ctx.answers,
            "pending_field": ctx.pending_field,
            "active_path": ctx.active_path,
            "path_locked": ctx.path_locked,
            "event": event or {},
            **edge.guard_args,
        }

        try:
            return bool(edge.guard_fn(guard_ctx))
        except Exception as e:
            logger.warning(f"Guard evaluation failed: {e}")
            return False

    def _select_edge_intelligently(
        self, edges: list, ctx: FlowContext, event: dict[str, Any] | None
    ) -> Any:
        """Use LLM to select the best edge based on context."""
        if not self._llm:
            # Fallback to first valid edge
            for edge in edges:
                if self._evaluate_guard(edge, ctx, event):
                    return edge
            return None

        # Build context for LLM
        edge_descriptions = []
        for i, edge in enumerate(edges):
            target_node = self._flow.nodes.get(edge.target)
            if target_node:
                edge_descriptions.append(
                    f"{i}. Go to '{target_node.label or target_node.id}' "
                    f"(guards: {edge.guard_args})"
                )

        try:
            instruction = (
                f"Based on the conversation context, which path should we take?\n"
                f"User intent: {ctx.user_intent}\n"
                f"Current answers: {ctx.answers}\n"
                f"Options:\n" + "\n".join(edge_descriptions) + "\n"
                "Reply with just the number of the best option."
            )
            response = self._llm.rewrite(instruction, "")

            # Parse response
            for i, edge in enumerate(edges):
                if str(i) in response:
                    return edge
        except Exception:
            pass

        # Fallback to guard evaluation
        for edge in edges:
            if self._evaluate_guard(edge, ctx, event):
                return edge
        return None

    def _get_unanswered_questions(self, ctx: FlowContext) -> list[dict[str, Any]]:
        """Get all unanswered question nodes."""
        unanswered = []

        for node_id, node in self._flow.nodes.items():
            if isinstance(node, QuestionNode):
                if node.key not in ctx.answers or ctx.answers[node.key] in (None, ""):
                    # Check if dependencies are met
                    if self._dependencies_met(node, ctx):
                        unanswered.append(
                            {
                                "id": node.id,
                                "key": node.key,
                                "prompt": node.prompt,
                                "priority": getattr(node, "priority", 100),
                            }
                        )

        return unanswered

    def _dependencies_met(self, node: QuestionNode, ctx: FlowContext) -> bool:
        """Check if a node's dependencies are satisfied."""
        # Check if node has dependency metadata
        deps = node.meta.get("dependencies", [])
        if not deps:
            return True

        for dep in deps:
            if dep not in ctx.answers or ctx.answers[dep] in (None, ""):
                return False

        return True

    def _select_next_question_intelligently(
        self,
        questions: list[dict[str, Any]],
        ctx: FlowContext,
    ) -> dict[str, Any] | None:
        """Use LLM to select the next best question."""
        if not questions:
            return None

        if not self._llm:
            # Fallback to priority
            return min(questions, key=lambda q: q["priority"])

        try:
            question_list = "\n".join(
                f"{i}. {q['prompt']} (key: {q['key']})" for i, q in enumerate(questions)
            )

            instruction = (
                f"Based on the conversation so far, which question should we ask next?\n"
                f"User intent: {ctx.user_intent or 'unknown'}\n"
                f"Already answered: {list(ctx.answers.keys())}\n"
                f"Available questions:\n{question_list}\n"
                f"Reply with just the number of the best question to ask next."
            )

            response = self._llm.rewrite(instruction, "")

            # Parse response
            for i, q in enumerate(questions):
                if str(i) in response:
                    return q
        except Exception:
            pass

        # Fallback to priority
        return min(questions, key=lambda q: q["priority"])

    def _suggest_actions(self, node: QuestionNode, ctx: FlowContext) -> list[str]:
        """Suggest possible actions for the current node."""
        suggestions = []

        # Add common suggestions based on node metadata
        if node.meta.get("allows_skip"):
            suggestions.append("skip")
        if node.meta.get("allows_multiple"):
            suggestions.append("add_more")
        if ctx.get_node_state(node.id).visits > 0:
            suggestions.append("change_answer")

        return suggestions

    def _handle_no_node(self, ctx: FlowContext) -> EngineResponse:
        """Handle case when there's no current node."""
        return EngineResponse(
            kind="escalate",
            message="I've lost track of where we are. Let me get someone to help.",
            node_id=None,
            metadata={"error": "no_current_node"},
        )

    def _handle_dead_end(self, ctx: FlowContext, node: Any) -> EngineResponse:
        """Handle dead end in the flow."""
        return EngineResponse(
            kind="escalate",
            message="I've reached an unexpected point. Let me transfer you to someone who can help.",
            node_id=node.id,
            metadata={"error": "dead_end"},
        )

    def _handle_no_valid_transition(self, ctx: FlowContext, node: Any) -> EngineResponse:
        """Handle case when no valid transition is found."""
        if self._strict_mode:
            return EngineResponse(
                kind="escalate",
                message="I couldn't determine the next step. Transferring to a specialist.",
                node_id=node.id,
                metadata={"error": "no_valid_transition"},
            )

        # In flexible mode, try to recover
        return self._find_next_question(ctx)

    def _identify_paths(self) -> list[str]:
        """Identify available paths in the flow."""
        # TODO: Implement path detection from flow structure
        return []

    def _find_next_question_simple(self, ctx: FlowContext) -> EngineResponse:
        """Simple fallback for finding next question."""
        for node_id, node in self._flow.nodes.items():
            if isinstance(node, QuestionNode):
                if node.key not in ctx.answers:
                    ctx.current_node_id = node.id
                    return self.process(ctx, None, None)

        return EngineResponse(
            kind="terminal",
            message="All questions answered!",
            node_id=ctx.current_node_id,
        )

    def _get_current_node(self, ctx: FlowContext) -> Any:
        """Get the current node from context."""
        if not ctx.current_node_id:
            return None
        return self._flow.nodes.get(ctx.current_node_id)

    def _generate_revisit_prompt(self, node: QuestionNode, ctx: FlowContext) -> str:
        """Generate prompt for revisiting a question."""
        prev_answer = ctx.answers.get(node.key)
        if prev_answer:
            return f"Earlier you mentioned '{prev_answer}' for this. Would you like to change it? {node.prompt}"
        return f"Let's revisit this question: {node.prompt}"

    def _make_casual(self, prompt: str, ctx: FlowContext) -> str:
        """Make prompt more casual."""
        if not self._llm:
            return prompt

        try:
            instruction = f"Make this question more casual and friendly: {prompt}"
            return self._llm.rewrite(instruction, "")
        except Exception:
            return prompt

    def _make_technical(self, prompt: str, ctx: FlowContext) -> str:
        """Make prompt more technical."""
        if not self._llm:
            return prompt

        try:
            instruction = f"Make this question more technical and precise: {prompt}"
            return self._llm.rewrite(instruction, "")
        except Exception:
            return prompt

    def _should_add_context(self, node: QuestionNode, ctx: FlowContext) -> bool:
        """Determine if context should be added to prompt."""
        # Add context for questions that depend on previous answers
        deps = node.meta.get("dependencies", [])
        return bool(deps and any(d in ctx.answers for d in deps))

    def _add_conversational_context(self, prompt: str, ctx: FlowContext) -> str:
        """Add conversational context to prompt."""
        if not self._llm:
            return prompt

        try:
            recent_context = ctx.get_recent_history(3)
            context_str = "\n".join(f"{h['role']}: {h['content'][:100]}" for h in recent_context)
            instruction = (
                f"Add brief context to this question based on the conversation:\n"
                f"Context: {context_str}\n"
                f"Question: {prompt}"
            )
            return self._llm.rewrite(instruction, "")
        except Exception:
            return prompt
