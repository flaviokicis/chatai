"""Session management interfaces and implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from app.core.agent_base import Agent
    from app.core.app_context import AppContext
    from app.core.inbound_message import InboundMessage  # type: ignore[import-untyped]
    from app.flow_core.state import FlowContext


class SessionPolicy(ABC):
    """Policy for determining session boundaries."""

    @abstractmethod
    def session_id(self, app_context: AppContext, agent: Agent, inbound: InboundMessage) -> str:
        """Generate session ID for the given context."""


class _WindowMeta(TypedDict):
    last_inbound_ts: str
    window_start_ts: str


class StableSessionPolicy(SessionPolicy):
    """Simple stable session policy."""

    def session_id(self, app_context: AppContext, agent: Agent, inbound: InboundMessage) -> str:
        return f"{inbound.channel}:{inbound.user_id}:stable"


class WindowedSessionPolicy(SessionPolicy):
    """Windowed session policy that creates new sessions after periods of inactivity."""

    def __init__(self, window_minutes: int = 30):
        self.window_minutes = window_minutes

    def session_id(self, app_context: AppContext, agent: Agent, inbound: InboundMessage) -> str:
        now = datetime.now(UTC)
        agent_type = f"{agent.__class__.__module__}.{agent.__class__.__name__}"
        meta_key = f"meta:{agent_type}"
        existing = app_context.store.load(inbound.user_id, meta_key)
        meta: _WindowMeta
        if isinstance(existing, dict):
            try:
                last_ts_str = str(existing.get("last_inbound_ts", ""))
                window_start_str = str(existing.get("window_start_ts", ""))
                last_ts = datetime.fromisoformat(last_ts_str)
                window_start_ts = datetime.fromisoformat(window_start_str)

                # Check if we're within the window
                if (now - last_ts).total_seconds() < self.window_minutes * 60:
                    # Update last timestamp but keep window
                    meta = _WindowMeta(
                        last_inbound_ts=now.isoformat(timespec="seconds"),
                        window_start_ts=window_start_ts.isoformat(timespec="seconds"),
                    )
                else:
                    # Start new window
                    meta = _WindowMeta(
                        last_inbound_ts=now.isoformat(timespec="seconds"),
                        window_start_ts=now.isoformat(timespec="seconds"),
                    )
            except (ValueError, KeyError):
                # Invalid existing data - start fresh
                meta = _WindowMeta(
                    last_inbound_ts=now.isoformat(timespec="seconds"),
                    window_start_ts=now.isoformat(timespec="seconds"),
                )
        else:
            # No existing data
            meta = _WindowMeta(
                last_inbound_ts=now.isoformat(timespec="seconds"),
                window_start_ts=now.isoformat(timespec="seconds"),
            )
        # Persist updated meta for next turn
        app_context.store.save(inbound.user_id, meta_key, dict(meta))  # type: ignore[arg-type]
        return f"{inbound.channel}:{inbound.user_id}:{agent_type}:{meta['window_start_ts']}"


class SessionManager(ABC):
    """Abstract interface for session management."""

    @abstractmethod
    def get_context(self, session_id: str) -> FlowContext | None:
        """Get flow context for a session."""

    @abstractmethod
    def save_context(self, session_id: str, context: FlowContext) -> None:
        """Save flow context for a session."""

    @abstractmethod
    def clear_context(self, session_id: str) -> None:
        """Clear flow context for a session."""
