from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, Response
from langchain.chat_models import init_chat_model
from twilio.twiml.messaging_response import MessagingResponse

from app.agents.base import BaseAgentDeps
from app.agents.sales_qualifier.factory import build_sales_qualifier_agent
from app.config.loader import load_json_config
from app.core.langchain_adapter import LangChainToolsLLM
from app.core.messages import InboundMessage
from app.core.state import InMemoryStore
from app.services.human_handoff import LoggingHandoff
from app.settings import get_settings
from app.whatsapp.twilio import TwilioWhatsAppHandler

if TYPE_CHECKING:
    from app.config.provider import AgentInstanceConfig, ChannelAgentConfig

app = FastAPI(title="Chatai Twilio Webhook", version="0.2.0")
logger = logging.getLogger("uvicorn.error")
app.state.config_provider = None  # type: ignore[attr-defined]
app.state.store = InMemoryStore()  # type: ignore[attr-defined]


def build_validation_url(request: Request, public_base_url: str | None) -> str:
    if public_base_url:
        base = public_base_url.rstrip("/")
        if request.url.query:
            return f"{base}{request.url.path}?{request.url.query}"
        return f"{base}{request.url.path}"
    return str(request.url)


@app.on_event("startup")
def _init_llm() -> None:
    settings = get_settings()
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key
    chat = init_chat_model(settings.llm_model, model_provider="google_genai")
    app.state.llm = LangChainToolsLLM(chat)
    app.state.llm_model = settings.llm_model
    logger.info("LLM initialized: model=%s provider=%s", settings.llm_model, "google_genai")
    # Load multitenant config from JSON if provided
    config_path = os.environ.get("CONFIG_JSON_PATH") or os.getenv("CONFIG_JSON_PATH")
    if config_path:
        app.state.config_provider = load_json_config(config_path)
        logger.info("Config provider initialized from %s", config_path)
    else:
        app.state.config_provider = load_json_config("config.json")
        logger.info("Config provider initialized from default config.json")


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@app.post("/webhooks/twilio/whatsapp")
async def twilio_whatsapp_webhook(
    request: Request,
    x_twilio_signature: str | None = Header(default=None, alias="X-Twilio-Signature"),
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
        # JSON payloads are currently acknowledged with 200 OK and no further processing
        return PlainTextResponse("ok")

    from_number = params.get("From", "")
    to_number = params.get("To", "")
    body_text = params.get("Body", "")
    logger.info("Incoming WhatsApp message from %s to %s: %s", from_number, to_number, body_text)

    # Resolve channel config and agent instance
    cfg = app.state.config_provider
    channel_id = to_number
    channel_cfg: ChannelAgentConfig | None = None
    if cfg and channel_id:
        channel_cfg = cfg.get_channel_config(
            tenant_id="default", channel_type="whatsapp", channel_id=channel_id
        )

    if not channel_cfg or not channel_cfg.agent_instances:
        logger.warning("No channel config/agent instances found for %s", channel_id)
        message_text = "Sorry, no agent is configured for this WhatsApp number."
        twiml = MessagingResponse()
        twiml.message(message_text)
        return Response(content=str(twiml), media_type="application/xml")

    # Pick default instance or first
    instance_id = channel_cfg.default_instance_id or channel_cfg.agent_instances[0].instance_id
    instance: AgentInstanceConfig | None = next(
        (i for i in channel_cfg.agent_instances if i.instance_id == instance_id), None
    )
    if not instance:
        instance = channel_cfg.agent_instances[0]

    # Build agent dependencies
    deps = BaseAgentDeps(store=app.state.store, llm=app.state.llm, handoff=LoggingHandoff())

    # Currently only sales_qualifier is supported
    if instance.agent_type != "sales_qualifier":
        logger.warning("Unsupported agent_type=%s", instance.agent_type)
        twiml = MessagingResponse()
        twiml.message("No suitable agent available.")
        return Response(content=str(twiml), media_type="application/xml")

    agent = build_sales_qualifier_agent(
        user_id=from_number or "unknown", deps=deps, instance=instance
    )

    inbound = InboundMessage(
        user_id=from_number or "unknown", text=body_text, channel="whatsapp", metadata={}
    )
    result = agent.handle(inbound)
    reply_text = (result.outbound.text if result.outbound else "") or ""

    twiml = MessagingResponse()
    twiml.message(reply_text)
    return Response(content=str(twiml), media_type="application/xml")
