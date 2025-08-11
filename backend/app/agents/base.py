from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.agent_base import Agent
from app.core.messages import AgentResult, OutboundMessage

if TYPE_CHECKING:  # pragma: no cover - import-time only for typing
    from app.core.llm import LLMClient
    from app.core.state import ConversationStore
    from app.core.tools import HumanHandoffTool


logger = logging.getLogger("uvicorn.error")


@dataclass(slots=True)
class BaseAgentDeps:
    store: ConversationStore
    llm: LLMClient
    handoff: HumanHandoffTool


class BaseAgent(Agent):
    def __init__(self, user_id: str, deps: BaseAgentDeps) -> None:
        super().__init__(user_id)
        self.deps = deps

    # Helper used by concrete agents
    def _escalate(self, reason: str, summary: dict[str, Any]) -> AgentResult:
        self.deps.handoff.escalate(self.user_id, reason, summary)
        return AgentResult(
            outbound=OutboundMessage(text="Transferring you to a human for further assistance."),
            handoff={"reason": reason, "summary": summary},
            state_diff={},
        )


class FlowAgent(BaseAgent):
    """Generic agent that delegates conversation flow to flow_core.LLMFlowEngine.

    Concrete agents can subclass this to add domain-specific business logic while
    reusing the common flow management capabilities.
    """

    agent_type = "flow"

    def __init__(
        self,
        user_id: str,
        deps: BaseAgentDeps,
        *,
        compiled_flow,
        path_flows: dict[str, object] | None = None,
    ) -> None:  # type: ignore[no-untyped-def]
        super().__init__(user_id, deps)
        self._compiled = compiled_flow
        self._path_flows = path_flows or {}

    def select_flow(self, stored_state: dict, message_text: str) -> object:
        """Generic multi-path flow selection. Override to customize path selection logic."""
        # If no path flows available, use main flow
        if not self._path_flows:
            return self._compiled

        # Load current path state
        active_path = stored_state.get("active_path")
        path_locked = bool(stored_state.get("path_locked", False))
        answers = dict(stored_state.get("answers", {}))

        # If path is locked, use that path's flow
        if path_locked and active_path in self._path_flows:
            return self._path_flows[active_path]

        # If no intention answer yet, use main flow
        if not answers.get("intention"):
            return self._compiled

        # Use LLM to select path based on intention
        paths = list(self._path_flows.keys())
        if not paths:
            return self._compiled

        # Get path selection prompt (can be overridden by subclasses)
        prompt = self._get_path_selection_prompt(message_text, answers, paths)

        from app.flow_core.tool_schemas import SelectFlowPath

        result = self.deps.llm.extract(prompt, [SelectFlowPath])
        chosen = result.get("path") if isinstance(result, dict) else None

        if isinstance(chosen, str) and chosen in paths:
            # Update state to lock this path
            stored_state["active_path"] = chosen
            stored_state["path_locked"] = True
            return self._path_flows[chosen]

        return self._compiled

    def _get_path_selection_prompt(self, message_text: str, answers: dict, paths: list[str]) -> str:
        """Get the prompt for path selection. Override in subclasses for domain-specific prompts."""
        return (
            f"Based on the user's intention and message, determine which conversation path to follow. "
            f"Be conservative - only select a path if you're confident.\n\n"
            f"User message: {message_text}\n"
            f"User answers so far: {answers}\n"
            f"Available conversation paths: {paths}\n\n"
            f"Select a path only if the user's intent clearly matches one of the available paths."
        )

    def load_agent_state(self, stored: dict) -> dict:
        """Load agent-specific state. Base implementation loads multi-path flow state."""
        if self._path_flows:
            return {
                "active_path": stored.get("active_path"),
                "path_locked": bool(stored.get("path_locked", False)),
            }
        return {}

    def save_agent_state(self, stored: dict, agent_state: dict) -> dict:
        """Save agent-specific state. Base implementation saves multi-path flow state."""
        if self._path_flows:
            stored.update(
                {
                    "active_path": agent_state.get("active_path"),
                    "path_locked": agent_state.get("path_locked", False),
                }
            )
        stored.update(agent_state)
        return stored

    def handle(self, message):  # type: ignore[no-untyped-def]
        from app.core.messages import AgentResult, OutboundMessage
        from app.flow_core.engine import LLMFlowEngine
        from app.flow_core.state import FlowContext

        # Load state
        stored = self.deps.store.load(self.user_id, self.agent_type) or {}
        agent_state = self.load_agent_state(stored)

        # Let agent select which flow to use
        selected_flow = self.select_flow(stored, message.text or "")

        # Create engine with selected flow
        engine = LLMFlowEngine(selected_flow, self.deps.llm, strict_mode=False)

        # Load or initialize context
        if "flow_context" in stored:
            ctx = FlowContext.from_dict(stored["flow_context"])
        else:
            ctx = engine.initialize_context()
            # Load legacy answers if they exist
            answers = dict(stored.get("answers", {}))
            ctx.answers.update(answers)

        # Process with engine
        response = engine.process(ctx, message.text or "")

        if response.kind == "terminal":
            return self._escalate("checklist_complete", {"answers": ctx.answers})

        # If we got a prompt and have a user message, and we're expecting an answer, use LLM to extract it
        # Only extract if this isn't the first interaction (when we're just asking the initial question)
        assistant_messages = [h for h in ctx.history if h.role == "assistant"]
        is_first_interaction = len(assistant_messages) == 0
        should_extract = (
            response.kind == "prompt"
            and message.text
            and ctx.pending_field
            and not is_first_interaction
        )

        if should_extract:
            from app.flow_core.llm_responder import LLMFlowResponder

            # Use LLM responder to extract answer
            responder = LLMFlowResponder(self.deps.llm)
            # Allow agents to specify toolsets: global + per-agent
            extra_tools = self.get_global_tools() + self.get_agent_tools()
            llm_response = responder.respond(
                response.message or "",
                ctx.pending_field,
                ctx,
                message.text,
                allowed_values=None,  # TODO: extract from node if needed
                extra_tools=extra_tools or None,
                agent_custom_instructions=self.get_agent_custom_instructions(),
            )

            # If LLM extracted an answer, process it with the engine
            if llm_response.updates and ctx.pending_field in llm_response.updates:
                answer = llm_response.updates[ctx.pending_field]
                old_node_id = ctx.current_node_id
                response = engine.process(
                    ctx,
                    None,
                    {
                        "answer": answer,
                        "tool_name": llm_response.tool_name,
                        "ack_message": llm_response.message,
                    },
                )

                # Check if we need to switch flows after the answer update
                updated_stored = {
                    "flow_context": ctx.to_dict(),
                    "answers": ctx.answers,
                }
                updated_stored = self.save_agent_state(updated_stored, agent_state)
                new_flow = self.select_flow(updated_stored, message.text or "")
                # Update agent_state with any changes from select_flow
                agent_state = self.load_agent_state(updated_stored)

                # If flow changed, switch to new flow and re-process
                flow_switched = False
                if new_flow != selected_flow:
                    flow_switched = True
                    engine = LLMFlowEngine(new_flow, self.deps.llm, strict_mode=False)
                    # Reset context for new flow but keep answers and history
                    old_answers = ctx.answers.copy()
                    old_history = ctx.history.copy()
                    ctx = engine.initialize_context()
                    ctx.answers.update(old_answers)
                    ctx.history = old_history
                    # Process from the beginning of the new flow
                    response = engine.process(ctx, None)

                # Check if the new flow resulted in terminal state
                if response.kind == "terminal":
                    return self._escalate("checklist_complete", {"answers": ctx.answers})

                # If we didn't advance to a new node (and didn't switch flows), use the LLM's message
                if (
                    not flow_switched
                    and response.kind == "prompt"
                    and ctx.current_node_id == old_node_id
                    and llm_response.message
                ):
                    response.message = llm_response.message
        # If this is the first interaction, add the assistant's response to history
        # so the next interaction knows it's not the first one
        elif response.kind == "prompt" and response.message:
            ctx.add_turn("assistant", response.message, response.node_id)

        # Save state
        updated_stored = {
            "flow_context": ctx.to_dict(),
            "answers": ctx.answers,  # Keep for backward compatibility
        }
        updated_stored = self.save_agent_state(updated_stored, agent_state)
        self.deps.store.save(self.user_id, self.agent_type, updated_stored)

        return AgentResult(
            outbound=OutboundMessage(text=response.message or ""), handoff=None, state_diff={}
        )

    # ---- Tool configuration hooks ----
    def get_global_tools(self) -> list[type]:
        """Global tools available to all agents by default.

        Keep empty by default to preserve contextual selection in the responder.
        Subclasses or a central registry can override to add safe, always-on tools.
        """
        return []

    def get_agent_tools(self) -> list[type]:
        """Agent-specific tools. Override in concrete agents to add domain tools."""
        return []

    def get_agent_custom_instructions(self) -> str | None:
        """Optional additional instruction text to prepend to tool-choice prompts.

        Subclasses may override to customize LLM behavior when choosing tools
        during question handling. Keep concise and high-signal.
        """
        return None
