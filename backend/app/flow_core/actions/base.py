"""Base interfaces for external action execution.

This module defines the core interfaces that all external actions must implement
to ensure proper integration with the LLM feedback loop.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionResult:
    """Result of an external action execution.
    
    This is the contract between action executors and the LLM feedback system.
    All results must be serializable and contain human-readable messages.
    """
    
    success: bool
    message: str  # Human-readable message for the user
    error: str | None = None  # Technical error details if failed
    data: dict[str, Any] | None = None  # Additional structured data
    
    @property
    def is_success(self) -> bool:
        """Check if the action was successful."""
        return self.success
    
    @property
    def is_failure(self) -> bool:
        """Check if the action failed."""
        return not self.success


class ActionExecutor(ABC):
    """Base interface for executing external actions.
    
    All external actions that require LLM feedback must implement this interface.
    This ensures proper separation of concerns and consistent error handling.
    """
    
    @abstractmethod
    async def execute(self, parameters: dict[str, Any], context: dict[str, Any]) -> ActionResult:
        """Execute the external action.
        
        Args:
            parameters: Action-specific parameters from the LLM
            context: Execution context (user_id, session_id, etc.)
            
        Returns:
            ActionResult with success/failure status and human-readable message
            
        Raises:
            Should not raise exceptions - all errors should be captured in ActionResult
        """
        pass
    
    @property
    @abstractmethod
    def action_name(self) -> str:
        """Unique identifier for this action type."""
        pass
