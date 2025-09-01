"""LLM-oriented flow engine for flexible, intelligent conversations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

# REMOVED: dev_config import - Use DEVELOPMENT_MODE environment variable instead


if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

    from .compiler import CompiledFlow

from .ir import DecisionNode, QuestionNode, TerminalNode
from .state import FlowContext, NodeStatus
from .tool_schemas import SelectFlowEdge, SelectNextQuestion

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
        llm: LLMClient,  # type: ignore[name-defined]
        *,
        strict_mode: bool = False,
    ) -> None:
        """
        Initialize the engine.

        Args:
            compiled: The compiled flow to execute
            llm: LLM client for intelligent decisions
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

        return ctx

    def process(
        self,
        ctx: FlowContext,
        user_message: str | None = None,
        event: dict[str, Any] | None = None,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
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
            return self._process_question_node(ctx, node, user_message, event, project_context)
        if isinstance(node, DecisionNode):
            return self._process_decision_node(ctx, node, event, project_context)
        if isinstance(node, TerminalNode):
            return self._process_terminal_node(ctx, node)
        logger.warning(f"Unknown node type: {type(node).__name__}")
        return EngineResponse(
            kind="escalate",
            message="Encontrei uma situação inesperada. Vou chamar alguém para ajudar.",
            node_id=node.id if node else None,
        )

    def _process_question_node(
        self,
        ctx: FlowContext,
        node: QuestionNode,
        user_message: str | None,
        event: dict[str, Any] | None,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
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
            return self._advance_from_node(ctx, node, event, project_context)

        # If we have a tool-driven event (without an explicit answer), handle accordingly
        if event and isinstance(event, dict) and event.get("tool_name"):
            handled = self._handle_tool_event(ctx, node, event, project_context)
            if handled:
                return handled



        # Generate the prompt (potentially contextual)
        prompt = self._generate_contextual_prompt(node, ctx, project_context)
        # Add light cohesion: if we just captured a value this turn, prepend a short acknowledgement
        return EngineResponse(
            kind="prompt",
            message=prompt,
            node_id=node.id,
            suggested_actions=self._suggest_actions(node, ctx),
        )

    def _handle_tool_event(
        self,
        ctx: FlowContext,
        node: QuestionNode,
        event: dict[str, Any],
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
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
        from app.settings import is_development_mode
        if is_development_mode():
            print(f"[DEBUG ENGINE] _handle_tool_event called with tool_name='{tool_name}', event={event}")
        # The runner no longer forwards LLM-generated text; all user-facing phrasing is done by the rewrite model.
        # Keep ack_text empty to avoid mixing tool LLM text with final outbound.
        ack_text = ""

        # Tool-provided messages are ignored at this layer to avoid double messaging.
        # The final outbound will be rewritten later with full context.
        def _with_ack(res: EngineResponse) -> EngineResponse:
            # Prefix a short acknowledgment to the outgoing prompt, if present
            if ack_text and res.kind == "prompt":
                ack_clean = ack_text.rstrip(".!?")
                if res.message:
                    res.message = f"{ack_clean}. {res.message}"
                else:
                    res.message = ack_clean
            return res

        if tool_name == "UnknownAnswer":
            # Get the reason for unknown answer
            unknown_reason = (event or {}).get("reason", "clarification_needed")

            if unknown_reason == "clarification_needed":
                # User needs clarification - stay on same question and regenerate prompt
                # The naturalization will use conversation context to provide clarification
                return EngineResponse(
                    kind="prompt",
                    message=self._generate_contextual_prompt(node, ctx, project_context),
                    node_id=node.id,
                    metadata={"is_clarification_response": True, "reason": unknown_reason},
                )

            if unknown_reason == "incoherent_or_confused":
                # User seems confused/disoriented - stay on same question but track confusion
                ctx.get_node_state(node.id).metadata["confusion_count"] = (
                    ctx.get_node_state(node.id).metadata.get("confusion_count", 0) + 1
                )

                # If user is repeatedly confused (3+ times), escalate to human
                if ctx.get_node_state(node.id).metadata.get("confusion_count", 0) >= 3:
                    return EngineResponse(
                        kind="escalate",
                        message="Vou te conectar com alguém que pode te ajudar melhor.",
                        node_id=node.id,
                        metadata={"reason": "repeated_confusion"},
                    )

                # Otherwise, stay on question and try to help with context
                return EngineResponse(
                    kind="prompt",
                    message=self._generate_contextual_prompt(node, ctx, project_context),
                    node_id=node.id,
                    metadata={"is_confusion_response": True, "reason": unknown_reason},
                )

            if unknown_reason == "requested_by_user":
                # User explicitly doesn't know and wants to skip
                # Handle based on question requirements

                # Check if question is required (default: False for conversational flexibility)
                node_required = getattr(node, "required", False)
                escalate_on_unknown = node_required or bool(
                    getattr(node, "meta", {}).get("escalate_on_unknown", False)
                )

                if escalate_on_unknown:
                    # Required question - escalate so user gets help
                    return EngineResponse(
                        kind="escalate",
                        message="Vou te conectar com alguém que pode ajudar com isso.",
                        node_id=node.id,
                        metadata={"reason": unknown_reason},
                    )

                # Optional question - defer this question and prefer advancing to a decision node if one is next
                # Do NOT mark as skipped; mark as deferred so we can revisit later if needed
                node_state = ctx.get_node_state(node.id)
                node_state.metadata["deferred"] = True

                # If there is a Decision node directly reachable from here, jump to it
                try:
                    edges = self._flow.edges_from.get(node.id, [])
                    for e in edges:
                        target = self._flow.nodes.get(getattr(e, "target", ""))
                        # Defer type checks to name to avoid tight coupling
                        if target and target.__class__.__name__ == "DecisionNode":
                            ctx.current_node_id = getattr(target, "id", None) or e.target
                            # Let the normal processing generate the decision prompt/options
                            return self.process(ctx, None, None, project_context)
                except Exception:
                    pass

                # Otherwise, fall back to default advancement
                return self._advance_from_node(ctx, node, event, project_context)

            # Fallback for any unexpected reason - treat as clarification needed
            return EngineResponse(
                kind="prompt",
                message=self._generate_contextual_prompt(node, ctx, project_context),
                node_id=node.id,
                metadata={"is_clarification_response": True, "reason": "fallback"},
            )

        if tool_name == "SkipQuestion":
            ctx.get_node_state(node.id).status = NodeStatus.SKIPPED
            target = event.get("skip_to") or event.get("navigation")
            if isinstance(target, str) and target:
                ctx.current_node_id = target
                return _with_ack(self.process(ctx, None, None, project_context))
            return self._advance_from_node(ctx, node, event, project_context)

        if tool_name == "RevisitQuestion":
            # Get the revisit details
            revisit_key = event.get("revisit_key") or event.get("question_key")
            revisit_value = event.get("revisit_value")
            revisit_updated = bool(event.get("revisit_updated"))

            # Special handling for path corrections (when selected_path is being revised)
            if revisit_key == "selected_path" and revisit_value:
                # This is actually a path correction
                # Try to normalize the path value
                normalized = self._normalize_path_value(revisit_value, ctx)
                if normalized:
                    ctx.answers["selected_path"] = normalized
                    ctx.active_path = normalized

                    # Navigate to the correct path
                    decision_node_id = self._find_decision_node_for_path(ctx)
                    if decision_node_id:
                        edges = self._flow.edges_from.get(decision_node_id, [])
                        for edge in edges:
                            if self._edge_matches_path(edge, normalized):
                                ctx.current_node_id = edge.target
                                return EngineResponse(
                                    kind="prompt",
                                    message=f"Certo, entendi! Vamos seguir pelo caminho de {normalized}.",
                                    node_id=edge.target,
                                )

            # Update the answer if a value was provided
            if isinstance(revisit_key, str) and revisit_value is not None:
                ctx.answers[revisit_key] = revisit_value
                revisit_updated = True

            # If the value was updated, remain on the current node and regenerate the prompt
            if revisit_updated:
                return EngineResponse(
                    kind="prompt",
                    message=self._generate_contextual_prompt(node, ctx, project_context),
                    node_id=node.id,
                )

            # If no value was provided, we need to navigate to the question to get the new value
            # Preferred: explicit target node id
            target = event.get("target_node") or event.get("navigation")

            # Fallback: find target node by provided question key
            if not target and isinstance(revisit_key, str) and revisit_key:
                # Search the compiled flow for a question node with this key
                for candidate in self._flow.nodes.values():
                    if candidate.__class__.__name__ == "QuestionNode":
                        if getattr(candidate, "key", None) == revisit_key:
                            target = candidate.id
                            break

            if isinstance(target, str) and target:
                ctx.current_node_id = target
                return _with_ack(self.process(ctx, None, None, project_context))

            # If no target could be determined, remain on current node
            return EngineResponse(
                kind="prompt",
                message=self._generate_contextual_prompt(node, ctx, project_context),
                node_id=node.id,
            )

        if tool_name == "RequestHumanHandoff":
            return EngineResponse(
                kind="escalate",
                message="Transferindo você para um atendente humano para mais assistência.",
                node_id=node.id,
                metadata={"reason": event.get("reason", "unspecified")},
            )

        if tool_name == "ProvideInformation":
            # Stay on the same node; simply regenerate the contextual prompt.
            # The rewriter will handle adding a brief empathetic acknowledgement.
            return EngineResponse(
                kind="prompt",
                message=self._generate_contextual_prompt(node, ctx, project_context),
                node_id=node.id,
            )



        if tool_name == "ConfirmCompletion":
            ctx.is_complete = True
            return EngineResponse(
                kind="terminal",
                message="All questions have been answered. Thank you!",
                node_id=node.id,
            )

        if tool_name == "NavigateFlow":
            target = event.get("target_node") or event.get("navigation")
            if isinstance(target, str) and target:
                ctx.current_node_id = target
                return _with_ack(self.process(ctx, None, None, project_context))
            return EngineResponse(
                kind="prompt",
                message=self._generate_contextual_prompt(node, ctx, project_context),
                node_id=node.id,
            )

        if tool_name == "SelectFlowPath":
            # Handle flow path selection - navigate back to decision node for re-evaluation
            selected_path = event.get("selected_path") or event.get("path")
            navigate_to_decision = event.get("navigate_to_decision", False)

            if selected_path and navigate_to_decision:
                # Try to find the decision node that should handle this path
                decision_node_id = self._find_decision_node_for_path(ctx)

                if decision_node_id:
                    # Navigate to the decision node to re-evaluate path selection
                    ctx.current_node_id = decision_node_id
                    # Process the decision node with the selected path
                    return self.process(ctx, None, {"selected_path": selected_path}, project_context)

            # If no navigation needed or decision node not found, stay on current node
            return EngineResponse(
                kind="prompt",
                message=self._generate_contextual_prompt(node, ctx, project_context),
                node_id=node.id,
            )

        if tool_name == "PathCorrection":
            # Handle path correction - navigate back to decision node or update path
            # Use normalized path for matching, not the original user input
            corrected_path = event.get("normalized_path") or event.get("corrected_path")

            if corrected_path:
                # Update the selected path
                ctx.answers["selected_path"] = corrected_path
                ctx.active_path = corrected_path

                # Try to find the decision node that led to this path
                decision_node_id = self._find_decision_node_for_path(ctx)

                if decision_node_id:
                    # Navigate to the target of the corrected path
                    edges = self._flow.edges_from.get(decision_node_id, [])

                    for edge in edges:
                        # Check if this edge matches the corrected path
                        if self._edge_matches_path(edge, corrected_path):
                            ctx.current_node_id = edge.target
                            # Process the new node to get its actual question
                            # Add acknowledgment as context for the rewriter
                            next_response = self.process(ctx, None, None, project_context)
                            if next_response.kind == "prompt" and next_response.message:
                                # Prepend acknowledgment to the actual question
                                ack_message = f"Certo, entendi! {corrected_path}."
                                next_response.message = f"{ack_message}\n\n{next_response.message}"
                            return next_response

            # If we can't find the right path, stay on current node
            return EngineResponse(
                kind="prompt",
                message=self._generate_contextual_prompt(node, ctx, project_context),
                node_id=node.id,
            )

        if tool_name == "RestartConversation":
            # Perform an in-place hard reset of context to the flow's entry
            # Keep flow_id and session_id; clear the rest
            entry_node_id = self._flow.entry
            ctx.current_node_id = entry_node_id
            ctx.answers.clear()
            ctx.node_states.clear()
            ctx.pending_field = None
            ctx.history.clear()
            ctx.turn_count = 0
            ctx.available_paths.clear()
            ctx.active_path = None
            ctx.path_confidence.clear()
            ctx.path_locked = False
            ctx.user_intent = None
            ctx.conversation_style = None
            ctx.clarification_count = 0
            ctx.is_complete = False
            ctx.escalation_reason = None

            # After reset, process from the entry to generate the initial prompt
            return _with_ack(self.process(ctx, None, None, project_context))

        # Unknown tool; let default prompt logic run
        return None

    def _process_decision_node(
        self,
        ctx: FlowContext,
        node: DecisionNode,
        event: dict[str, Any] | None,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    ) -> EngineResponse:
        """Process a decision node with LLM-aware edge selection."""
        ctx.mark_node_visited(node.id)
        # Ensure no question field is pending while choosing a path
        ctx.pending_field = None

        # Get edges from this node
        edges = self._flow.edges_from.get(node.id, [])
        if not edges:
            return self._handle_dead_end(ctx, node)

        # Branch behavior by decision type
        decision_type = getattr(node, "decision_type", "automatic")

        if decision_type == "automatic":
            # Preserve legacy/automatic behavior
            if self._strict_mode:
                for edge in edges:
                    if self._evaluate_guard(edge, ctx, event):
                        ctx.current_node_id = edge.target
                        return self.process(ctx, None, None, project_context)
                return self._handle_no_valid_transition(ctx, node, project_context)

            selected_edge = self._select_edge_intelligently(edges, ctx, event, project_context)
            if selected_edge:
                ctx.current_node_id = selected_edge.target
                return self.process(ctx, None, None, project_context)

            # Fallback to guard evaluation (non-strict automatic mode)
            for edge in edges:
                if self._evaluate_guard(edge, ctx, event):
                    ctx.current_node_id = edge.target
                    return self.process(ctx, None, None, project_context)
            return self._handle_no_valid_transition(ctx, node, project_context)

        # Handle llm_assisted vs user_choice differently
        if decision_type == "llm_assisted":
            # LLM-assisted should be processed internally, never shown to user
            selected_edge = self._select_edge_with_llm_decision(node, edges, ctx, event, project_context)
            if selected_edge:
                ctx.current_node_id = selected_edge.target
                return self.process(ctx, None, None, project_context)
            # If LLM can't decide, fall back to first valid edge or error
            valid_edges = [e for e in edges if self._evaluate_guard(e, ctx, event)]
            if valid_edges:
                ctx.current_node_id = valid_edges[0].target
                return self.process(ctx, None, None, project_context)
            return self._handle_no_valid_transition(ctx, node, project_context)

        # decision_type is user_choice -> interactive path selection
        options: list[dict[str, Any]] = []
        valid_edges: list[Any] = []
        for edge in edges:
            if self._evaluate_guard(edge, ctx, event):
                valid_edges.append(edge)
            target_node = self._flow.nodes.get(edge.target)
            label = None
            if getattr(edge, "condition_description", None):
                label = str(edge.condition_description)
            elif getattr(edge, "label", None):
                label = str(edge.label)
            elif target_node and getattr(target_node, "label", None):
                label = str(target_node.label)
            elif target_node:
                label = str(getattr(target_node, "id", "opção"))
            else:
                label = "opção"

            # Extract human-readable path name from condition_description
            # e.g., "Caminho: campo/futebol" -> "campo/futebol"
            path_name = label
            if label and ":" in label:
                path_name = label.split(":", 1)[1].strip()

            # Use path name as key for LLM selection, but keep node ID for navigation
            options.append({"key": path_name, "label": label, "edge": edge, "target_node": edge.target})

        # Store human-readable path names for LLM selection
        ctx.available_paths = [opt["key"] for opt in options]
        # Store mapping from path names to labels
        ctx.path_labels = {opt["key"]: opt["label"] for opt in options}

        # First, try to resolve an explicit candidate (can be node id, label, or key)
        selected_edge = None
        if isinstance(event, dict):
            path_meta = event.get("path") or event.get("selected_path")
            if isinstance(path_meta, str) and path_meta.strip():
                selected_edge = self._select_edge_by_candidate(path_meta, options)
        if not selected_edge:
            ans_val = ctx.answers.get("selected_path")
            if isinstance(ans_val, str) and ans_val.strip():
                selected_edge = self._select_edge_by_candidate(ans_val, options)

        if selected_edge:
            ctx.current_node_id = selected_edge.target
            # If we deferred a previous question that fed into this decision, backfill a plausible intent
            try:
                # Find last question node marked as deferred without answer
                for state in ctx.node_states.values():
                    if state.metadata.get("deferred") and state.status != NodeStatus.COMPLETED:
                        qnode = self._flow.nodes.get(state.node_id)
                        if qnode and getattr(qnode, "key", None) and qnode.key not in ctx.answers:
                            # Use the selected path's label as a concise intent if it exists
                            label = None
                            try:
                                # Resolve label from options list by matching edge
                                for opt in options:
                                    if opt.get("edge") is selected_edge:
                                        label = str(opt.get("label") or "").strip()
                                        break
                            except Exception:
                                label = None
                            if isinstance(label, str) and label:
                                ctx.answers[qnode.key] = label
                                state.status = NodeStatus.COMPLETED
                                state.metadata.pop("deferred", None)
                        break
            except Exception:
                pass
            return self.process(ctx, None, None, project_context)

        if len(valid_edges) == 1:
            ctx.current_node_id = valid_edges[0].target
            return self.process(ctx, None, None, project_context)

        if self._strict_mode or decision_type == "user_choice":
            return EngineResponse(
                kind="prompt",
                message=self._generate_decision_prompt(node, options, ctx),
                node_id=node.id,
                metadata={"needs_path_selection": True},
            )

        selected_edge = self._select_edge_intelligently(edges, ctx, event)
        if selected_edge:
            ctx.current_node_id = selected_edge.target
            return self.process(ctx, None, None, project_context)

        return EngineResponse(
            kind="prompt",
            message=self._generate_decision_prompt(node, options, ctx),
            node_id=node.id,
            metadata={"needs_path_selection": True},
        )

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
            message=node.reason or "Conversa concluída",
            node_id=node.id,
            metadata={"final_answers": ctx.answers},
        )

    def _advance_from_node(
        self,
        ctx: FlowContext,
        node: Any,
        event: dict[str, Any] | None,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
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
                        # Format as separate sentences with proper spacing
                        ack_clean = ack_text.rstrip(".!?")
                        res.message = f"{ack_clean}. {res.message}"
                    else:
                        res.message = ack_text
            return res

        if not edges:
            # No outgoing edges, find next question or complete
            return _with_ack(self._find_next_question(ctx, project_context))

        # Evaluate edges
        for edge in edges:
            if self._evaluate_guard(edge, ctx, event):
                ctx.current_node_id = edge.target
                return _with_ack(self.process(ctx, None, None, project_context))

        # No valid edge, stay on current node
        return _with_ack(self.process(ctx, None, None, project_context))

    def _find_next_question(
        self,
        ctx: FlowContext,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    ) -> EngineResponse:
        """Find the next unanswered question intelligently."""
        if self._strict_mode:
            # Fallback to simple priority-based selection in strict mode
            return self._find_next_question_simple(ctx, project_context)

        # Use LLM to determine best next question based on context
        unanswered = self._get_unanswered_questions(ctx)
        if not unanswered:
            ctx.is_complete = True
            return EngineResponse(
                kind="terminal",
                message="Todas as perguntas foram respondidas. Obrigado!",
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
            return self.process(ctx, None, None, project_context)

        return EngineResponse(
            kind="terminal",
            message="Reuni todas as informações necessárias. Obrigado!",
            node_id=ctx.current_node_id,
        )

    def _generate_contextual_prompt(self, node: QuestionNode, ctx: FlowContext, project_context: ProjectContext | None = None) -> str:
        """Generate a context-aware prompt."""
        base_prompt = node.prompt

        if self._strict_mode:
            return base_prompt

        # Check if this is a revisit
        node_state = ctx.get_node_state(node.id)
        if node_state.visits > 1:
            return self._generate_revisit_prompt(node, ctx)

        # Add context if relevant
        if ctx.turn_count > 0 and self._should_add_context(node, ctx):
            base_prompt = self._add_conversational_context(base_prompt, ctx)

        # Return the base prompt directly - let the rewriter handle naturalization
        # The rewriter has better context and rules for preserving questions
        return base_prompt





    def _validate_answer(self, node: QuestionNode, answer: Any, ctx: FlowContext) -> bool:
        """Validate an answer using the node's validator."""
        if not node.validator:
            return True

        # TODO: Implement validator execution
        # For now, return True
        return True

    def _generate_validation_prompt(self, node: QuestionNode, answer: Any, ctx: FlowContext) -> str:
        """Generate a prompt for validation failure."""


        try:
            instruction = (
                f"The user provided '{answer}' for '{node.prompt}' but it's not valid. "
                f"Generate a friendly message asking them to provide a valid answer. "
                f"Be specific about what's expected."
            )
            return self._llm.rewrite(instruction, "")
        except Exception:
            return f"Não consegui processar '{answer}'. Você pode tentar novamente? {node.prompt}"

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

    def _select_edge_with_llm_decision(
        self,
        node: Any,
        edges: list,
        ctx: FlowContext,
        event: dict[str, Any] | None,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    ) -> Any:
        """Use LLM responder to make a decision for llm_assisted decision nodes."""
        from .llm_responder import LLMFlowResponder
        from .tool_schemas import SelectFlowPath

        decision_prompt = getattr(node, "decision_prompt", None)
        if not decision_prompt:
            # Fall back to standard edge selection
            return self._select_edge_intelligently(edges, ctx, event, project_context)

        # Get the user's last message for context
        last_user_message = ""
        for turn in reversed(ctx.history):
            if turn.role == "user":
                last_user_message = turn.content
                break

        if not last_user_message:
            # No user message to base decision on, use fallback
            return self._select_edge_intelligently(edges, ctx, event, project_context)

        # Set up available paths in context for the responder
        path_options = []
        for edge in edges:
            condition_desc = getattr(edge, "condition_description", "")
            if condition_desc:
                # Extract path name from condition description
                if ":" in condition_desc:
                    path_name = condition_desc.split(":", 1)[1].strip()
                else:
                    path_name = condition_desc
                path_options.append(path_name)
            else:
                target_node = self._flow.nodes.get(edge.target)
                if target_node:
                    path_options.append(target_node.label or target_node.id)
                else:
                    path_options.append(f"option_{edge.target}")

        # Update context with available paths
        ctx.available_paths = path_options

        # Use the responder to make the decision
        responder = LLMFlowResponder(self._llm, use_all_tools=False)

        # Create a custom prompt that includes the decision prompt
        decision_question = f"{decision_prompt}\n\nBased on the user's response, which path should we take?"

        try:
            response = responder.respond(
                prompt=decision_question,
                pending_field=None,
                ctx=ctx,
                user_message=last_user_message,
                extra_tools=[SelectFlowPath]
            )

            # If we got a path selection, find the corresponding edge
            if response.tool_name == "SelectFlowPath" and "selected_path" in response.updates:
                selected_path = response.updates["selected_path"]
                for i, path in enumerate(path_options):
                    if path == selected_path:
                        return edges[i]
        except Exception as e:
            import logging
            logging.warning(f"LLM responder decision failed: {e}")

        # No confident selection, use fallback
        return self._select_edge_intelligently(edges, ctx, event, project_context)

    def _select_edge_intelligently(
        self,
        edges: list,
        ctx: FlowContext,
        event: dict[str, Any] | None,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    ) -> Any:
        """Use LLM to select the best edge based on context."""


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

            # Add project context if available to help with decision-making
            if project_context and project_context.has_decision_context():
                context_prompt = project_context.get_decision_context_prompt()
                instruction = f"{instruction}\n{context_prompt}"

            result = self._llm.extract(instruction, [SelectFlowEdge])
            if result.get("__tool_name__") == "SelectFlowEdge":
                selected_index = result.get("selected_edge_index")
                if selected_index is not None and 0 <= selected_index < len(edges):
                    return edges[selected_index]
        except Exception:
            pass

        # No confident selection
        return None

    # ---- Helpers for decision routing ----
    def _match_path_key(self, candidate: str, available: list[str]) -> str | None:
        """Match a free-text candidate to one of the available path keys."""
        if not isinstance(candidate, str) or not available:
            return None
        cand = candidate.strip().lower()
        if cand in (a.lower() for a in available):
            # Exact (case-insensitive) match
            return next(a for a in available if a.lower() == cand)
        # Try substring match case-insensitively
        for a in available:
            al = a.lower()
            if cand in al or al in cand:
                return a
        return None

    def _generate_decision_prompt(
        self,
        node: DecisionNode,
        options: list[dict[str, Any]],
        ctx: FlowContext,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    ) -> str:
        # If a custom decision_prompt is provided in the flow, naturalize it
        if getattr(node, "decision_prompt", None):
            base_prompt = str(node.decision_prompt)
            try:
                # Get recent conversation history for context
                recent_history = ctx.get_recent_history(3)
                conversation_context = [{"role": h.get("role", ""), "content": h.get("content", "")} for h in recent_history]

                # Get the last user message if available
                last_user_message = None
                for turn in reversed(ctx.history):
                    if getattr(turn, "role", "") == "user":
                        last_user_message = getattr(turn, "content", "")
                        break

                return base_prompt
            except Exception:
                return base_prompt

        # Default fallback: concise neutral question listing options
        labels = [str(o["label"]) for o in options]
        base = "Qual caminho faz mais sentido para a gente seguir?"
        if not labels:
            try:
                # Get conversation context
                recent_history = ctx.get_recent_history(3)
                conversation_context = [{"role": h.get("role", ""), "content": h.get("content", "")} for h in recent_history]
                last_user_message = None
                for turn in reversed(ctx.history):
                    if getattr(turn, "role", "") == "user":
                        last_user_message = getattr(turn, "content", "")
                        break

                return base
            except Exception:
                return base
        if len(labels) == 1:
            opt_text = labels[0]
        else:
            opt_text = ", ".join(labels[:-1]) + f" ou {labels[-1]}"

        full_prompt = f"{base} {opt_text}."
        try:
            # Get conversation context
            recent_history = ctx.get_recent_history(3)
            conversation_context = [{"role": h.get("role", ""), "content": h.get("content", "")} for h in recent_history]
            last_user_message = None
            for turn in reversed(ctx.history):
                if getattr(turn, "role", "") == "user":
                    last_user_message = getattr(turn, "content", "")
                    break

            return full_prompt
        except Exception:
            return full_prompt

    def _select_edge_by_candidate(self, candidate: str, options: list[dict[str, Any]]):
        """Resolve an edge by matching the candidate against option key, label, or target node id.

        Supports selecting by:
        - key (path name like "campo/futebol")
        - label (full label with "Caminho: ...")
        - target node id (for backward compatibility)
        """
        cand = (candidate or "").strip()
        if not cand:
            return None

        # 1) Match by path name (key)
        for opt in options:
            if cand == str(opt.get("key", "")):
                return opt.get("edge")

        # 2) Match by label (case-insensitive or contains)
        cand_lower = cand.lower()
        for opt in options:
            label = str(opt.get("label", ""))
            lab_lower = label.lower()
            if cand_lower == lab_lower or cand_lower in lab_lower:
                return opt.get("edge")

        # 3) Match by target node id (backward compatibility)
        for opt in options:
            target_node = opt.get("target_node")
            if target_node and cand == str(target_node):
                return opt.get("edge")

        # 4) Partial matching for path names
        for opt in options:
            key = str(opt.get("key", ""))
            key_lower = key.lower()
            if cand_lower in key_lower or key_lower in cand_lower:
                return opt.get("edge")

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

            result = self._llm.extract(instruction, [SelectNextQuestion])
            if result.get("__tool_name__") == "SelectNextQuestion":
                selected_index = result.get("selected_question_index")
                if selected_index is not None and 0 <= selected_index < len(questions):
                    return questions[selected_index]
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
        # Check if this is an empty flow (no nodes or no entry)
        if not self._flow.nodes or not self._flow.entry or self._flow.entry not in self._flow.nodes:
            return EngineResponse(
                kind="prompt",
                message="Ola! O fluxo está vazio. Vamos começar a construir juntos! Como você gostaria que eu cumprimente seus clientes?",
                node_id=None,
                metadata={"empty_flow": True, "flow_building_mode": True},
            )
        
        return EngineResponse(
            kind="escalate",
            message="Perdi o contexto de onde estamos. Vou chamar alguém para ajudar.",
            node_id=None,
            metadata={"error": "no_current_node"},
        )

    def _handle_dead_end(self, ctx: FlowContext, node: Any) -> EngineResponse:
        """Handle dead end in the flow."""
        return EngineResponse(
            kind="escalate",
            message="Cheguei a um ponto inesperado. Vou transferir você para alguém que possa ajudar.",
            node_id=node.id,
            metadata={"error": "dead_end"},
        )

    def _handle_no_valid_transition(
        self,
        ctx: FlowContext,
        node: Any,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    ) -> EngineResponse:
        """Handle case when no valid transition is found."""
        if self._strict_mode:
            return EngineResponse(
                kind="escalate",
                message="Não consegui determinar o próximo passo. Transferindo para um especialista.",
                node_id=node.id,
                metadata={"error": "no_valid_transition"},
            )

        # In flexible mode, try to recover
        return self._find_next_question(ctx, project_context)

    def _find_next_question_simple(
        self,
        ctx: FlowContext,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    ) -> EngineResponse:
        """Simple fallback for finding next question."""
        for node_id, node in self._flow.nodes.items():
            if isinstance(node, QuestionNode):
                if node.key not in ctx.answers:
                    ctx.current_node_id = node.id
                    return self.process(ctx, None, None, project_context)

        return EngineResponse(
            kind="terminal",
            message="Todas as perguntas foram respondidas!",
            node_id=ctx.current_node_id,
        )

    def _get_current_node(self, ctx: FlowContext) -> Any:
        """Get the current node from context."""
        if not ctx.current_node_id:
            return None
        return self._flow.nodes.get(ctx.current_node_id)

    def _generate_revisit_prompt(self, node: QuestionNode, ctx: FlowContext) -> str:
        """Generate prompt for revisiting a question."""
        # Naturalize the prompt but don't add extra framing
        base_prompt = node.prompt
        try:
            # Get conversation context for revisit
            recent_history = ctx.get_recent_history(3)
            conversation_context = [{"role": h.get("role", ""), "content": h.get("content", "")} for h in recent_history]
            last_user_message = None
            for turn in reversed(ctx.history):
                if getattr(turn, "role", "") == "user":
                    last_user_message = getattr(turn, "content", "")
                    break

            return base_prompt
        except Exception:
            return base_prompt

    def _should_add_context(self, node: QuestionNode, ctx: FlowContext) -> bool:
        """Determine if context should be added to prompt."""
        # Add context for questions that depend on previous answers
        deps = node.meta.get("dependencies", [])
        return bool(deps and any(d in ctx.answers for d in deps))

    def _add_conversational_context(self, prompt: str, ctx: FlowContext) -> str:
        """Add conversational context to prompt."""


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

    def _find_decision_node_for_path(self, ctx: FlowContext) -> str | None:
        """Find the decision node that controls path selection."""
        # Look for decision nodes in the flow
        for node_id, node in self._flow.nodes.items():
            if isinstance(node, DecisionNode):
                # Check if this decision node has edges to paths
                edges = self._flow.edges_from.get(node_id, [])
                for edge in edges:
                    if hasattr(edge, "condition_description"):
                        # This looks like a path decision node
                        return node_id
        return None

    def _edge_matches_path(self, edge: Any, path: str) -> bool:
        """Check if an edge matches a given path name."""
        if not edge or not path:
            return False

        path_lower = path.lower()

        # Check condition_description
        if hasattr(edge, "condition_description"):
            desc = str(edge.condition_description).lower()
            # Remove "caminho: " prefix if present
            desc = desc.replace("caminho:", "").strip()
            if path_lower == desc or path_lower in desc or desc in path_lower:
                return True

        # Check label
        if hasattr(edge, "label"):
            label = str(edge.label).lower()
            if path_lower == label or path_lower in label or label in path_lower:
                return True

        # Check guard args for path hints
        if hasattr(edge, "guard_args") and isinstance(edge.guard_args, dict):
            if_cond = edge.guard_args.get("if", "").lower()
            if path_lower in if_cond:
                return True

        return False

    def _normalize_path_value(self, value: str, ctx: FlowContext) -> str | None:
        """Let the LLM decide which available path best matches the value.
        
        Delegates to LLM for intelligent path matching.
        """
        if not value or not ctx.available_paths:
            return value

        try:
            # Build instruction for LLM to choose best path
            available_paths_str = ", ".join(f"'{path}'" for path in ctx.available_paths)

            instruction = f"""The user said: "{value}"
            
Available paths: {available_paths_str}
            
Which available path best matches what the user meant? 
Return EXACTLY one of the available paths, or 'none' if no good match.
            
Respond with just the path name, nothing else."""

            result = self._llm.rewrite(instruction, "")
            normalized = result.strip().strip("'\"")

            # Verify the result is actually one of the available paths
            if normalized in ctx.available_paths:
                return normalized
            if normalized.lower() == "none":
                return value  # No good match, return original
            # LLM returned something invalid, fall back to original
            return value

        except Exception:
            # If LLM call fails, return original input
            return value
