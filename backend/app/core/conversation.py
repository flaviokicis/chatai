from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING

from app.core.messages import AgentResult, InboundMessage, OutboundMessage
from app.core.session import SessionPolicy, StableSessionPolicy
from app.services.rate_limiter import RateLimitParams

if TYPE_CHECKING:
    from app.core.agent_base import Agent
    from app.core.app_context import AppContext


logger = logging.getLogger(__name__)


def _resolve_session_policy(app_context: AppContext) -> SessionPolicy:
    if app_context.session_policy is not None:
        return app_context.session_policy
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

    # Hard cap inbound text length for safety/cost control
    max_input_chars = 500
    if inbound.text and len(inbound.text) > max_input_chars:
        inbound.text = inbound.text[:max_input_chars]

    # Centralized rate limiting (per-tenant, per-user)
    try:
        limiter = getattr(app_context, "rate_limiter", None)
        provider = getattr(app_context, "config_provider", None)
        tenant_id = "default"
        # Safely access tenant_id from typed metadata
        if hasattr(inbound, "metadata") and inbound.metadata.tenant_id:
            tenant_id = str(inbound.metadata.tenant_id)

        if limiter is not None:
            limits_raw = provider.get_rate_limit_params(tenant_id) if provider else None
            params = RateLimitParams(
                window_seconds=int((limits_raw or {}).get("window_seconds", 60)),
                max_requests_per_user=int((limits_raw or {}).get("max_requests_per_user", 20)),
                max_requests_per_tenant=int((limits_raw or {}).get("max_requests_per_tenant", 200)),
            )
            allowed, _rem_u, _rem_t = limiter.allow(
                tenant_id=tenant_id, user_id=inbound.user_id, params=params
            )
            if not allowed:
                return AgentResult(
                    outbound=OutboundMessage(
                        text="You have reached the message limit. Please try again in a minute."
                    ),
                    handoff=None,
                    state_diff={},
                )
    except Exception:
        # Never block the turn on rate limiter failures
        logger.warning(
            "Rate limiter check failed; proceeding without limiting", exc_info=True
        )

    history = None
    if hasattr(app_context.store, "get_message_history"):
        try:
            history = app_context.store.get_message_history(session_id)
            if hasattr(history, "add_user_message"):
                history.add_user_message(inbound.text)
        except Exception:
            history = None

    result = agent.handle(inbound)

    # Flow core is now pure - no channel-specific rewriting here

    if history and hasattr(history, "add_ai_message") and result.outbound:
        with suppress(Exception):
            history.add_ai_message(result.outbound.text)

    return result
