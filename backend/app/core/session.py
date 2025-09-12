from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol, TypedDict

if TYPE_CHECKING:
    from app.core.agent_base import Agent
    from app.core.app_context import AppContext
    from app.core.messages import InboundMessage


class SessionPolicy(Protocol):
    def session_id(self, app_context: AppContext, agent: Agent, inbound: InboundMessage) -> str: ...


def _agent_type(agent: Agent) -> str:
    return agent.get_agent_type()


class StableSessionPolicy:
    """Simple policy: one session per channel+user+agent."""

    def session_id(self, app_context: AppContext, agent: Agent, inbound: InboundMessage) -> str:
        agent_type = _agent_type(agent)
        return f"{inbound.channel}:{inbound.user_id}:{agent_type}"


class _WindowMeta(TypedDict):
    last_inbound_ts: str  # ISO8601 UTC
    window_start_ts: str  # ISO8601 UTC


class WindowedSessionPolicy:
    """Windowed policy: session rotates after inactivity greater than duration."""

    def __init__(self, duration: timedelta) -> None:
        self.duration = duration

    def session_id(self, app_context: AppContext, agent: Agent, inbound: InboundMessage) -> str:
        now = datetime.now(UTC)
        agent_type = _agent_type(agent)
        meta_key = f"meta:{agent_type}"
        existing = app_context.store.load(inbound.user_id, meta_key)
        meta: _WindowMeta
        if isinstance(existing, dict):
            try:
                last_ts_str = str(existing.get("last_inbound_ts", ""))
                window_start_str = str(existing.get("window_start_ts", ""))
                last_dt = datetime.fromisoformat(last_ts_str) if last_ts_str else None
                window_dt = datetime.fromisoformat(window_start_str) if window_start_str else None
            except Exception:
                last_dt = None
                window_dt = None
            if not window_dt:
                window_dt = now
            if not last_dt or (now - last_dt) > self.duration:
                window_dt = now
            meta = _WindowMeta(
                last_inbound_ts=now.isoformat(timespec="seconds"),
                window_start_ts=window_dt.isoformat(timespec="seconds"),
            )
        else:
            meta = _WindowMeta(
                last_inbound_ts=now.isoformat(timespec="seconds"),
                window_start_ts=now.isoformat(timespec="seconds"),
            )
        # Persist updated meta for next turn
        app_context.store.save(inbound.user_id, meta_key, dict(meta))  # type: ignore[arg-type]
        return f"{inbound.channel}:{inbound.user_id}:{agent_type}:{meta['window_start_ts']}"
