"""Action registry for managing external action executors.

This module provides a centralized registry for all external action executors,
ensuring clean separation of concerns and easy extensibility.
"""

from __future__ import annotations

import logging

from app.core.llm import LLMClient

from .base import ActionExecutor
from .flow_modification import FlowModificationExecutor

logger = logging.getLogger(__name__)


class ActionRegistry:
    """Registry for external action executors.

    This class manages all available action executors and provides
    a clean interface for executing actions by name.
    """

    def __init__(self, llm_client: LLMClient):
        """Initialize the action registry.

        Args:
            llm_client: LLM client for actions that need it
        """
        self._executors: dict[str, ActionExecutor] = {}
        self._register_default_executors(llm_client)

    def _register_default_executors(self, llm_client: LLMClient) -> None:
        """Register the default set of action executors.

        Args:
            llm_client: LLM client for executors that need it
        """
        # Register flow modification executor
        flow_mod_executor = FlowModificationExecutor(llm_client)
        self.register(flow_mod_executor)

        logger.info(f"Registered {len(self._executors)} action executors")

    def register(self, executor: ActionExecutor) -> None:
        """Register an action executor.

        Args:
            executor: The executor to register

        Raises:
            ValueError: If an executor with the same name is already registered
        """
        action_name = executor.action_name
        if action_name in self._executors:
            raise ValueError(f"Action executor '{action_name}' is already registered")

        self._executors[action_name] = executor
        logger.debug(f"Registered action executor: {action_name}")

    def get_executor(self, action_name: str) -> ActionExecutor | None:
        """Get an action executor by name.

        Args:
            action_name: Name of the action

        Returns:
            The executor if found, None otherwise
        """
        return self._executors.get(action_name)

    def has_executor(self, action_name: str) -> bool:
        """Check if an executor is registered for the given action.

        Args:
            action_name: Name of the action

        Returns:
            True if an executor is registered, False otherwise
        """
        return action_name in self._executors

    def list_actions(self) -> list[str]:
        """Get a list of all registered action names.

        Returns:
            List of registered action names
        """
        return list(self._executors.keys())
