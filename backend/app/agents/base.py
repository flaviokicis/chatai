from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.agent_base import Agent
from app.core.messages import AgentResult, InboundMessage, OutboundMessage
from app.flow_core.runner import FlowTurnRunner
from app.flow_core.state import FlowContext

# Tool imports removed - no longer needed

if TYPE_CHECKING:  # pragma: no cover - import-time only for typing
    from app.core.llm import LLMClient
    from app.core.state import ConversationStore
    from app.core.tools import HumanHandoffTool
    from app.flow_core.compiler import CompiledFlow


logger = logging.getLogger(__name__)


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

        # Clear chat history to prevent context bleeding when user re-engages
        if hasattr(self.deps.store, "clear_chat_history"):
            try:
                deleted_keys = self.deps.store.clear_chat_history(self.user_id, self.agent_type)
                logger.info(
                    "Cleared %d chat history keys for user %s after handoff",
                    deleted_keys,
                    self.user_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to clear chat history after handoff for user %s: %s", self.user_id, e
                )

        return AgentResult(
            outbound=OutboundMessage(
                text="Transferindo você para um atendente humano para mais assistência."
            ),
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
        compiled_flow: CompiledFlow,
        path_flows: dict[str, CompiledFlow] | None = None,
        strict_mode: bool = False,
    ) -> None:  # type: ignore[no-untyped-def]
        super().__init__(user_id, deps)
        self._compiled = compiled_flow
        self._path_flows = path_flows or {}
        self._strict_mode = bool(strict_mode)

    def select_flow(self, stored_state: dict, message_text: str) -> CompiledFlow:
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

    def handle(self, message: InboundMessage) -> AgentResult:  # type: ignore[no-untyped-def]
        # Load state
        stored = self.deps.store.load(self.user_id, self.agent_type) or {}
        agent_state = self.load_agent_state(stored)

        # Select flow (may use existing answers/state)
        selected_flow = self.select_flow(stored, message.text or "")

        # Initialize unified runner (mirrors CLI behavior)
        runner = FlowTurnRunner(selected_flow, self.deps.llm, strict_mode=self._strict_mode)

        # Load or initialize context
        if "flow_context" in stored:
            ctx = FlowContext.from_dict(stored["flow_context"])
        else:
            ctx = runner.initialize_context()
            # Load legacy answers if they exist
            answers = dict(stored.get("answers", {}))
            ctx.answers.update(answers)

        # Extract project context from typed message metadata
        project_context = message.metadata.project_context if hasattr(message, "metadata") else None

        # Process one turn
        result = runner.process_turn(ctx, message.text or "", project_context=project_context)

        # Handle terminal state - NO LONGER clear context, just mark as complete
        if result.terminal:
            # Mark context as complete but keep it active for follow-up questions
            ctx._is_complete = True
            # Store the completion state but don't escalate
            stored_out = {
                "flow_context": ctx.to_dict(),
                "answers": ctx.answers,
                "flow_completed": True,  # Track that flow reached terminal
            }
            stored_out = self.save_agent_state(stored_out, agent_state)
            self.deps.store.save(self.user_id, self.agent_type, stored_out)
            
            # Return the terminal message without clearing context
            return AgentResult(
                outbound=OutboundMessage(text=result.assistant_message or ""),
                handoff=None,
                state_diff={},
            )

        # Handle escalation request
        if result.escalate:
            return self._escalate("user_requested_handoff", {"answers": ctx.answers})

        # After applying updates, re-evaluate path selection if any answers changed
        if result.answers_diff:
            updated_stored = {
                "flow_context": ctx.to_dict(),
                "answers": ctx.answers,
            }
            updated_stored = self.save_agent_state(updated_stored, agent_state)
            new_flow = self.select_flow(updated_stored, message.text or "")
            agent_state = self.load_agent_state(updated_stored)

            if new_flow != selected_flow:
                # Switch to new flow while preserving answers/history
                new_runner = FlowTurnRunner(new_flow, self.deps.llm, strict_mode=self._strict_mode)
                old_answers = ctx.answers.copy()
                old_history = ctx.history.copy()
                ctx = new_runner.initialize_context()  # Re-assign ctx
                ctx.answers.update(old_answers)
                ctx.history = old_history
                # Produce next prompt in the new path (no new user input)
                result = new_runner.process_turn(ctx, None)

        # Persist state
        stored_out = {
            "flow_context": ctx.to_dict(),
            "answers": ctx.answers,
        }
        stored_out = self.save_agent_state(stored_out, agent_state)
        self.deps.store.save(self.user_id, self.agent_type, stored_out)

        # Return outbound message
        return AgentResult(
            outbound=OutboundMessage(text=result.assistant_message or ""),
            handoff=None,
            state_diff={},
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
