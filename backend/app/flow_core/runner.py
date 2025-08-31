"""FlowTurnRunner - High-level orchestrator for flow conversations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

# REMOVED: dev_config import - Use DEVELOPMENT_MODE environment variable instead

from .engine import LLMFlowEngine
from .llm_responder import LLMFlowResponder
from .state import FlowContext
from app.core.thought_tracer import ThoughtTracer


# Type alias for tool event callbacks
ToolEventCallback = Callable[[str, dict[str, Any]], bool]


@dataclass(slots=True)
class TurnResult:
    """Result of processing a single conversation turn."""

    assistant_message: str | None
    answers_diff: dict[str, Any]
    tool_name: str | None
    escalate: bool
    terminal: bool
    ctx: FlowContext  # updated context


class FlowTurnRunner:
    """High-level orchestrator that combines engine + responder for simple turn processing."""

    def __init__(
        self,
        compiled_flow,  # type: ignore[no-untyped-def]
        llm: LLMClient,  # type: ignore[name-defined]
        *,
        extra_tools: list[type] | None = None,
        instruction_prefix: str | None = None,
        strict_mode: bool = False,
        thought_tracer: ThoughtTracer | None = None,
        on_tool_event: ToolEventCallback | None = None,
    ) -> None:
        """Initialize the runner.

        Args:
            compiled_flow: The compiled flow to execute
            llm: LLM client for intelligent responses
            extra_tools: Additional tools to make available
            instruction_prefix: Custom instruction text to prepend
            strict_mode: If True, enforce traditional state machine behavior
            thought_tracer: Optional thought tracer for capturing reasoning
            on_tool_event: Optional callback for intercepting tool events
        """
        self._engine = LLMFlowEngine(compiled_flow, llm, strict_mode=strict_mode)
        self._responder = LLMFlowResponder(llm, thought_tracer=thought_tracer)
        self._compiled = compiled_flow
        self._extra_tools = extra_tools or []
        self._instruction_prefix = instruction_prefix
        self._thought_tracer = thought_tracer
        self._on_tool_event = on_tool_event

    def initialize_context(self, existing_context: FlowContext | None = None) -> FlowContext:
        """Initialize or restore flow context."""
        return self._engine.initialize_context(existing_context)

    def process_turn(
        self,
        ctx: FlowContext,
        user_message: str | None = None,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    ) -> TurnResult:
        """Process a single conversation turn.

        Args:
            ctx: The flow context (will be modified in place)
            user_message: Optional user message

        Returns:
            TurnResult with assistant message, answers diff, and updated context
        """
        # Store initial answers to calculate diff
        initial_answers = dict(ctx.answers)

        # Get engine response (prompt or terminal)
        engine_response = self._engine.process(ctx, user_message, project_context=project_context)

        if engine_response.kind == "terminal":
            return TurnResult(
                assistant_message=engine_response.message,
                answers_diff={},
                tool_name=None,
                escalate=False,
                terminal=True,
                ctx=ctx,
            )

        if engine_response.kind == "escalate":
            return TurnResult(
                assistant_message=engine_response.message,
                answers_diff={},
                tool_name=None,
                escalate=True,
                terminal=False,
                ctx=ctx,
            )

        # If no user message, just return the prompt (record assistant turn for first interaction)
        if not user_message or not self._responder:
            if engine_response.kind == "prompt" and engine_response.message:
                ctx.add_turn("assistant", engine_response.message, engine_response.node_id)
            return TurnResult(
                assistant_message=engine_response.message,
                answers_diff={},
                tool_name=None,
                escalate=False,
                terminal=False,
                ctx=ctx,
            )

        # ALWAYS process user messages through the responder, including first interaction
        # This allows the LLM to extract intent from the very first user message
        # (In WhatsApp/chat, users always initiate - there's no "show greeting first" scenario)

        # Get allowed values from current node
        allowed_values = self._get_allowed_values(ctx)

        # Use responder to process user input
        responder_result = self._responder.respond(
            engine_response.message or "",
            ctx.pending_field,
            ctx,
            user_message,
            allowed_values,
            extra_tools=self._extra_tools or None,
            agent_custom_instructions=self._instruction_prefix,
        )

        # Generic tool event callback: allow callers to intercept any tool
        # without altering engine state (e.g., EnterTrainingMode, custom control flows)
        if self._on_tool_event and responder_result.tool_name:
            metadata = responder_result.metadata or {}
            intercepted = self._on_tool_event(responder_result.tool_name, metadata)
            if intercepted:
                return TurnResult(
                    assistant_message=None,
                    answers_diff={},
                    tool_name=responder_result.tool_name,
                    escalate=False,
                    terminal=False,
                    ctx=ctx,
                )

        # Apply updates to context first
        for k, v in responder_result.updates.items():
            ctx.answers[k] = v

        # Debug logging (after updates are applied)
        from app.settings import is_development_mode
        if is_development_mode():
            print(f"[DEBUG] Tool chosen: {responder_result.tool_name}")
            print(f"[DEBUG] Updates: {responder_result.updates}")
            print(f"[DEBUG] Metadata: {responder_result.metadata}")
            # Include reasoning if provided by tool LLM
            reasoning = None
            if isinstance(responder_result.metadata, dict):
                reasoning = responder_result.metadata.get("reasoning")
            if not reasoning:
                # Some tools put reasoning at top level (e.g., SelectFlowPath)
                reasoning = (
                    responder_result.metadata.get("reason")
                    if isinstance(responder_result.metadata, dict)
                    else None
                )
            print(f"[DEBUG] Reasoning: {reasoning}")
            print(f"[DEBUG] Current answers (after update): {ctx.answers}")
            print(f"[DEBUG] Pending field: {ctx.pending_field}")

        # Special handling for RevisitQuestion: if the model indicated a revisit,
        # apply the new value if provided and navigate to the appropriate node.
        revisit_value: str | None = None
        revisit_key = None
        if responder_result.tool_name == "RevisitQuestion" and responder_result.metadata:
            revisit_key = responder_result.metadata.get(
                "revisit_key"
            ) or responder_result.metadata.get("question_key")

            if isinstance(revisit_key, str):
                # Check if the responder already provided the value in updates
                if revisit_key in responder_result.updates:
                    revisit_value = responder_result.updates[revisit_key]
                else:
                    # Try to get explicit value from tool metadata
                    explicit_value = responder_result.metadata.get("revisit_value")
                    if isinstance(explicit_value, str) and explicit_value.strip():
                        revisit_value = explicit_value.strip()
                        # Apply the value immediately
                        ctx.answers[revisit_key] = revisit_value
        # Forward responder outcome to engine
        engine_event: dict[str, object] = {"tool_name": responder_result.tool_name or ""}
        if ctx.pending_field and ctx.pending_field in responder_result.updates:
            engine_event["answer"] = responder_result.updates[ctx.pending_field]
        
        # Pass all updates to engine event so decision nodes can access path selections
        # and other non-pending-field updates
        for key, value in responder_result.updates.items():
            if key != ctx.pending_field:  # Avoid duplicating the answer field
                engine_event[key] = value
        # Attach reasoning to engine event for downstream visibility
        if responder_result.metadata and isinstance(responder_result.metadata, dict):
            if responder_result.metadata.get("reasoning"):
                engine_event["reasoning"] = responder_result.metadata.get("reasoning")
            elif responder_result.metadata.get("reason"):
                engine_event["reasoning"] = responder_result.metadata.get("reason")
        # Do not pass any text from tool LLM; the rewrite layer will craft the user-facing message.
        # We only pass structured metadata to drive engine behavior.
        # Pass structured metadata
        if responder_result.metadata:
            engine_event.update(responder_result.metadata)
        # Pass revisit outcome so engine can avoid navigation if we already updated
        if revisit_key and revisit_value:
            engine_event["revisit_key"] = revisit_key
            engine_event["revisit_value"] = revisit_value
            engine_event["revisit_updated"] = True

        # Process the tool event with engine
        final_response = self._engine.process(ctx, None, engine_event)

        # Record assistant message in history (will be updated with rewritten version by channel adapter)
        if final_response.message:
            ctx.add_turn("assistant", final_response.message, final_response.node_id)

        # Calculate answers diff
        answers_diff = {}
        for k, v in ctx.answers.items():
            if k not in initial_answers or initial_answers[k] != v:
                answers_diff[k] = v

        return TurnResult(
            assistant_message=final_response.message,
            answers_diff=answers_diff,
            tool_name=responder_result.tool_name,
            escalate=responder_result.escalate or final_response.kind == "escalate",
            terminal=final_response.kind == "terminal",
            ctx=ctx,
        )

    def _get_allowed_values(self, ctx: FlowContext) -> list[str] | None:
        """Extract allowed values from current node."""
        if not ctx.current_node_id:
            return None

        node = self._compiled.nodes.get(ctx.current_node_id)
        if not node:
            return None

        # Check node.allowed_values first
        vals = getattr(node, "allowed_values", None)
        if isinstance(vals, list) and all(isinstance(v, str) for v in vals):
            return vals

        # Check meta.allowed_values for backward compatibility
        meta = getattr(node, "meta", None)
        if isinstance(meta, dict):
            mvals = meta.get("allowed_values")
            if isinstance(mvals, list) and all(isinstance(v, str) for v in mvals):
                return mvals  # type: ignore[return-value]

        return None

    def _get_allowed_values_for_key(self, question_key: str) -> list[str] | None:
        """Find allowed values for a question by its key in the compiled flow."""
        # Look up the node by key
        for node_id, node in self._compiled.nodes.items():
            key = getattr(node, "key", None)
            if key == question_key:
                # Check node.allowed_values
                vals = getattr(node, "allowed_values", None)
                if isinstance(vals, list) and all(isinstance(v, str) for v in vals):
                    return vals
                meta = getattr(node, "meta", None)
                if isinstance(meta, dict):
                    mvals = meta.get("allowed_values")
                    if isinstance(mvals, list) and all(isinstance(v, str) for v in mvals):
                        return mvals
                return None
        return None
