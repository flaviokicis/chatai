from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse
from langchain.chat_models import init_chat_model
from twilio.twiml.messaging_response import MessagingResponse

from app.agents.base import BaseAgentDeps
from app.agents.sales_qualifier.factory import build_sales_qualifier_agent
from app.core.app_context import get_app_context
from app.core.conversation import run_agent_turn
from app.core.langchain_adapter import LangChainToolsLLM
from app.core.messages import InboundMessage
from app.core.session import WindowedSessionPolicy
from app.services.human_handoff import LoggingHandoff
from app.settings import get_settings

from .twilio import TwilioWhatsAppHandler

if TYPE_CHECKING:
    from app.config.provider import AgentInstanceConfig, ChannelAgentConfig, ConfigProvider
    from app.core.app_context import AppContext


logger = logging.getLogger("uvicorn.error")


def build_twiml_response(text: str) -> Response:
    """Create a simple TwiML message response."""
    twiml = MessagingResponse()
    twiml.message(text)
    return Response(content=str(twiml), media_type="application/xml")


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
    if not x_twilio_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Twilio-Signature header",
        )

    settings = get_settings()
    twilio = TwilioWhatsAppHandler(settings)

    params = await twilio.validate_and_parse(request, x_twilio_signature)
    if not params:
        return PlainTextResponse("ok")

    sender_number = params.get("From", "")
    receiver_number = params.get("To", "")
    message_text = params.get("Body", "")
    logger.info(
        "Incoming WhatsApp message from %s to %s: %s", sender_number, receiver_number, message_text
    )

    app_context = get_app_context(request.app)  # type: ignore[arg-type]
    channel_config, available_channels = get_channel_config_for_channel(
        app_context, receiver_number
    )
    if not channel_config or not channel_config.agent_instances:
        logger.warning(
            "No channel config/agent instances found for %s (available=%s)",
            receiver_number,
            ", ".join(available_channels) if available_channels else "<none>",
        )
        return build_twiml_response("Sorry, no agent is configured for this WhatsApp number.")

    agent_instance = select_agent_instance(channel_config)
    agent_deps = build_agent_dependencies(app_context, agent_instance)

    if agent_instance.agent_type != "sales_qualifier":
        logger.warning("Unsupported agent_type=%s", agent_instance.agent_type)
        return build_twiml_response("No suitable agent available.")

    agent = build_sales_qualifier_agent(
        user_id=sender_number or "unknown", deps=agent_deps, instance=agent_instance
    )

    inbound = InboundMessage(
        user_id=sender_number or "unknown", text=message_text, channel="whatsapp", metadata={}
    )
    # Apply WhatsApp-specific 24h windowed session policy only here
    result = run_agent_turn(
        app_context,
        agent,
        inbound,
        policy=WindowedSessionPolicy(duration=timedelta(hours=24)),
    )
    reply_text = (result.outbound.text if result.outbound else "") or ""
    return build_twiml_response(reply_text)
