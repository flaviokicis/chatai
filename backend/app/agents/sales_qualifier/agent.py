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
    ) -> None:
        super().__init__(user_id, deps, compiled_flow=compiled_flow, path_flows=path_compiled or {})

    def _get_path_selection_prompt(self, message_text: str, answers: dict, paths: list[str]) -> str:
        """Sales-specific path selection prompt."""
        return (
            "You are a sales qualification system. Based on the customer's intention and latest message, "
            "determine which conversation path to follow. Be conservative - only select a path if you're confident.\n\n"
            f"Customer message: {message_text}\n"
            f"Customer answers so far: {answers}\n"
            f"Available conversation paths: {paths}\n\n"
            "Select a path only if the customer's intent clearly matches one of the available paths."
        )
