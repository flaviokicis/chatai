from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from app.core.session import SessionPolicy, StableSessionPolicy

if TYPE_CHECKING:
    from app.core.messages import InboundMessage

if TYPE_CHECKING:
    from app.core.agent_base import Agent
    from app.core.app_context import AppContext
    from app.core.messages import AgentResult


def _resolve_session_policy(app_context: AppContext) -> SessionPolicy:
    if app_context.session_policy is not None:
        return app_context.session_policy  # type: ignore[return-value]
    return StableSessionPolicy()


def run_agent_turn(
    app_context: AppContext,
    agent: Agent,
    inbound: InboundMessage,
    policy: SessionPolicy | None = None,
) -> AgentResult:
    """Run one agent turn and record history using provided or resolved session policy."""
    policy = policy or _resolve_session_policy(app_context)
    session_id = policy.session_id(app_context, agent, inbound)

    history = None
    if hasattr(app_context.store, "get_message_history"):
        try:
            history = app_context.store.get_message_history(session_id)  # type: ignore[attr-defined]
            if hasattr(history, "add_user_message"):
                history.add_user_message(inbound.text)
        except Exception:
            history = None

    result = agent.handle(inbound)

    if history and hasattr(history, "add_ai_message") and result.outbound:
        with suppress(Exception):
            history.add_ai_message(result.outbound.text)

    return result
