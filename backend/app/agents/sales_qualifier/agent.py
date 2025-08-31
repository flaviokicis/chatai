from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.base import FlowAgent

if TYPE_CHECKING:  # import only for typing
    from app.agents.base import BaseAgentDeps


class SalesQualifierAgent(FlowAgent):
    """Sales qualification agent with intelligent path selection based on customer intent."""

    agent_type = "sales_qualifier"

    def __init__(
        self,
        user_id: str,
        deps: BaseAgentDeps,
        compiled_flow: object,
        path_compiled: dict[str, object] | None = None,
        *,
        strict_mode: bool = False,
    ) -> None:
        super().__init__(
            user_id,
            deps,
            compiled_flow=compiled_flow,
            path_flows=path_compiled or {},
            strict_mode=strict_mode,
        )

    def get_agent_custom_instructions(self) -> str | None:
        """Sales qualification specific instructions for LLM tool selection."""
        return (
            "SALES QUALIFICATION INSTRUCTIONS:\n"
            "- When making path selection decisions, you must be 90%+ confident before choosing a path\n"
            "- If a customer says generic things like 'comprar LEDs' without specific application details, "
            "choose paths that allow MORE qualification (like 'ginásio/quadra', 'galpão', 'campo') rather than "
            "generic paths that skip qualification\n"
            "- Always prioritize gathering more information over making assumptions\n"
            "- Lead qualification is the primary goal - collect specific application, budget, timeline details"
        )

    def _get_path_selection_prompt(self, message_text: str, answers: dict, paths: list[str]) -> str:
        """Sales-specific path selection prompt."""
        return (
            "You are a sales qualification system. Based on the customer's intention and latest message, "
            "determine which conversation path to follow. Be conservative - only select a path if you're 90%+ confident.\n\n"
            f"Customer message: {message_text}\n"
            f"Customer answers so far: {answers}\n"
            f"Available conversation paths: {paths}\n\n"
            "IMPORTANT: If the customer provided generic interest (like 'comprar LEDs'), choose paths that "
            "enable more qualification questions rather than paths that lead directly to handoff. "
            "Select a path only if the customer's intent clearly and specifically matches one of the available paths."
        )
