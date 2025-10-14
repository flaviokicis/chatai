"""External action execution domain.

This module defines the interfaces and implementations for executing external actions
that require feedback to the LLM. All external actions must implement the ActionExecutor
interface to ensure proper result handling and truthful LLM responses.
"""

from .base import ActionExecutor, ActionResult
from .registry import ActionRegistry

__all__ = [
    "ActionExecutor",
    "ActionRegistry",
    "ActionResult",
]
