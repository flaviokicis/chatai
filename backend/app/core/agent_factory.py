"""Agent factory for creating appropriate agents based on flow configuration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # FlowAgent removed - using FlowProcessor directly
    pass


class SalesQualificationAgentWrapper:
    """Lightweight wrapper providing sales qualification behavior."""

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

    def get_agent_tools(self) -> list[type]:
        """Get agent-specific tools."""
        return []  # No additional tools for now

logger = logging.getLogger(__name__)


class FlowAgentFactory:
    """Factory for creating flow agents based on flow configuration."""

    def __init__(self) -> None:
        """Initialize the agent factory."""

    def create_agent_for_flow(self, flow_definition: dict[str, Any], user_id: str) -> Any | None:
        """
        Create an appropriate agent for the given flow definition.
        
        Args:
            flow_definition: The flow configuration
            user_id: The user ID for the agent
            
        Returns:
            An appropriate agent instance or None if no specific agent needed
        """
        # Extract flow ID to determine agent type
        flow_id = flow_definition.get("id", "")

        # For now, we'll use heuristics based on flow ID or content
        # In the future, this could be configured in the database

        if self._is_sales_qualification_flow(flow_definition):
            logger.info(f"Creating SalesQualifierAgent for flow {flow_id}")
            # For now, return a simple wrapper that provides the interface
            # In the future, this could create full agent instances
            return SalesQualificationAgentWrapper()

        logger.info(f"No specific agent needed for flow {flow_id}")
        return None

    def _is_sales_qualification_flow(self, flow_definition: dict[str, Any]) -> bool:
        """Determine if this is a sales qualification flow."""
        flow_id = flow_definition.get("id", "").lower()
        flow_name = flow_definition.get("metadata", {}).get("name", "").lower()

        # Check for sales/qualification keywords
        sales_keywords = [
            "sales", "vendas", "qualifier", "qualifica",
            "atendimento", "luminarias", "lead", "prospect"
        ]

        return any(keyword in flow_id or keyword in flow_name for keyword in sales_keywords)
