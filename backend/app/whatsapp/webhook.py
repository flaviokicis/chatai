from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
from langchain.chat_models import init_chat_model

from app.agents.base import BaseAgentDeps
from app.agents.sales_qualifier.factory import build_sales_qualifier_agent
from app.core.app_context import get_app_context
from app.core.channel_adapter import ConversationalRewriter
from app.core.conversation import run_agent_turn
from app.core.langchain_adapter import LangChainToolsLLM
from app.core.messages import InboundMessage
from app.core.session import WindowedSessionPolicy
from app.services.human_handoff import LoggingHandoff
from app.settings import get_settings

from .adapter import WhatsAppAdapter
from .twilio_adapter import TwilioWhatsAppAdapter

if TYPE_CHECKING:
    from app.config.provider import AgentInstanceConfig, ChannelAgentConfig, ConfigProvider
    from app.core.app_context import AppContext


logger = logging.getLogger("uvicorn.error")


def _get_adapter(settings) -> WhatsAppAdapter:  # type: ignore[no-untyped-def]
    # For now, always Twilio; can be swapped by returning a different adapter here
    return TwilioWhatsAppAdapter(settings)


def get_channel_config_for_channel(
    app_context: AppContext, channel_id: str
) -> tuple[ChannelAgentConfig | None, list[str]]:
    """Fetch channel configuration for a WhatsApp number.

    Returns (config, available_channels) for diagnostics.
    """
    provider: ConfigProvider | None = app_context.config_provider
    if not provider or not channel_id:
        return None, []
    config = provider.get_channel_config(
        tenant_id="default", channel_type="whatsapp", channel_id=channel_id
    )
    if config:
        return config, []
    try:
        tenant_cfg = provider.get_tenant_config("default")
        available = [f"{ch.channel_type}:{ch.channel_id}" for ch in tenant_cfg.channels]
    except Exception:
        available = []
    return None, available


def select_agent_instance(channel_config: ChannelAgentConfig) -> AgentInstanceConfig:
    """Select the desired agent instance from a channel config.

    Prefers the configured default, otherwise the first instance.
    """
    preferred_id = (
        channel_config.default_instance_id or channel_config.agent_instances[0].instance_id
    )
    chosen = next(
        (i for i in channel_config.agent_instances if i.instance_id == preferred_id), None
    )
    return chosen or channel_config.agent_instances[0]


def build_agent_dependencies(
    app_context: AppContext, agent_instance: AgentInstanceConfig
) -> BaseAgentDeps:
    """Construct BaseAgentDeps with an optional per-instance LLM override."""
    llm_client = app_context.llm
    if agent_instance.llm and agent_instance.llm.model:
        provider = agent_instance.llm.provider or "google_genai"
        chat_override = init_chat_model(agent_instance.llm.model, model_provider=provider)
        llm_client = LangChainToolsLLM(chat_override)
    return BaseAgentDeps(store=app_context.store, llm=llm_client, handoff=LoggingHandoff())


## The webhook should not handle persistence of history; that is centralized in the framework


async def handle_twilio_whatsapp_webhook(
    request: Request, x_twilio_signature: str | None
) -> Response:
    # Validation is delegated to adapter; keep header presence check minimal
    if not x_twilio_signature:
        # Adapter will raise HTTP 400 if required; but allow test monkeypatch to proceed
        pass

    settings = get_settings()
    adapter = _get_adapter(settings)

    params = await adapter.validate_and_parse(request, x_twilio_signature)
    if not params:
        return PlainTextResponse("ok")

    sender_number = params.get("From", "")
    receiver_number = params.get("To", "")
    message_text = params.get("Body", "")
    MAX_INPUT_CHARS = 500
    if len(message_text) > MAX_INPUT_CHARS:
        message_text = message_text[:MAX_INPUT_CHARS]
    logger.info(
        "Incoming WhatsApp message from %s to %s: %s", sender_number, receiver_number, message_text
    )

    app_context = get_app_context(request.app)  # type: ignore[arg-type]
    # Per-tenant discovery: for now the WhatsApp number belongs to a single tenant
    # If multi-tenant routing is added, replace this with real lookup.
    tenant_id = "default"
    channel_config, available_channels = get_channel_config_for_channel(
        app_context, receiver_number
    )
    if not channel_config or not channel_config.agent_instances:
        logger.warning(
            "No channel config/agent instances found for %s (available=%s)",
            receiver_number,
            ", ".join(available_channels) if available_channels else "<none>",
        )
        return adapter.build_sync_response(
            "Sorry, no agent is configured for this WhatsApp number."
        )

    agent_instance = select_agent_instance(channel_config)
    agent_deps = build_agent_dependencies(app_context, agent_instance)

    if agent_instance.agent_type != "sales_qualifier":
        logger.warning("Unsupported agent_type=%s", agent_instance.agent_type)
        return adapter.build_sync_response("No suitable agent available.")

    agent = build_sales_qualifier_agent(
        user_id=sender_number or "unknown", deps=agent_deps, instance=agent_instance
    )

    inbound = InboundMessage(
        user_id=sender_number or "unknown", text=message_text, channel="whatsapp", metadata={}
    )

    # Pass tenant_id via metadata for centralized rate limiting in run_agent_turn
    inbound.metadata["tenant_id"] = tenant_id
    # Apply WhatsApp-specific 24h windowed session policy only here
    result = run_agent_turn(
        app_context,
        agent,
        inbound,
        policy=WindowedSessionPolicy(duration=timedelta(hours=24)),
    )
    # Use shared rewriter system for WhatsApp conversational output
    reply_text = (result.outbound.text if result.outbound else "") or ""

    # Setup rewriter with app context LLM
    rewriter = ConversationalRewriter(getattr(app_context, "llm", None))

    # Build chat history from Redis/session if available
    history = None
    if hasattr(app_context.store, "get_message_history"):
        try:
            session_id = WindowedSessionPolicy(duration=timedelta(hours=24)).session_id(
                app_context, agent, inbound
            )
            history = app_context.store.get_message_history(session_id)  # type: ignore[attr-defined]
        except Exception:
            history = None

    # Build chat history and rewrite message
    chat_history = rewriter.build_chat_history(
        langchain_history=history, latest_user_input=message_text
    )

    # Rewrite into multi-message plan
    messages = rewriter.rewrite_message(reply_text, chat_history, enable_rewrite=True)

    # First message is sent synchronously
    first_message = messages[0] if messages else {"text": reply_text, "delay_ms": 0}
    sync_reply = str(first_message.get("text", reply_text)).strip() or reply_text

    logger.info("Sending WhatsApp reply: %r (total messages: %d)", sync_reply, len(messages))

    # Send follow-ups if there are any
    if len(messages) > 1:
        try:
            adapter.send_followups(sender_number, receiver_number, messages)
        except Exception as e:
            logger.warning("Failed to send WhatsApp follow-ups: %s", e)

    return adapter.build_sync_response(sync_reply)
