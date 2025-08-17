from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

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
from app.db.models import MessageDirection, MessageStatus
from app.db.repository import (
    find_channel_instance_by_identifier,
    get_or_create_contact,
    get_or_create_thread,
)
from app.db.session import create_session
from app.services.human_handoff import LoggingHandoff
from app.services.message_logging_service import message_logging_service
from app.services.tenant_config_service import TenantConfigService
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

    # Get tenant configuration from database using channel identifier
    project_context = None
    tenant_id: UUID | None = None

    session = create_session()
    try:
        tenant_service = TenantConfigService(session)
        project_context = tenant_service.get_project_context_by_channel_identifier(receiver_number)

        if not project_context:
            logger.warning("No tenant configuration found for WhatsApp number: %s", receiver_number)
            return adapter.build_sync_response(
                "Desculpe, este número do WhatsApp não está configurado."
            )

        tenant_id = project_context.tenant_id
        logger.info("Found tenant %s for channel %s", tenant_id, receiver_number)

    except Exception as e:
        logger.error("Failed to get tenant configuration: %s", e)
        return adapter.build_sync_response("Desculpe, ocorreu um erro interno. Tente novamente.")
    finally:
        session.close()

    # Use mock config fallback for now until full migration
    # TODO: Remove this fallback once all channels are in database
    try:
        channel_config, available_channels = get_channel_config_for_channel(
            app_context, receiver_number
        )
        if channel_config and channel_config.agent_instances:
            agent_instance = select_agent_instance(channel_config)
            agent_deps = build_agent_dependencies(app_context, agent_instance)
        else:
            # Create default agent configuration for database-managed channels
            agent_deps = BaseAgentDeps(
                store=app_context.store,
                llm=LangChainToolsLLM(
                    init_chat_model("gemini-2.5-flash", model_provider="google_genai")
                ),
                handoff=LoggingHandoff(),
            )
            # Create a basic agent instance config
            from app.config.provider import AgentInstanceConfig

            agent_instance = AgentInstanceConfig(
                instance_id="default_sales_qualifier", agent_type="sales_qualifier"
            )
    except Exception as e:
        logger.warning("Mock config fallback failed, using database-only mode: %s", e)
        # Create default agent configuration for database-managed channels
        agent_deps = BaseAgentDeps(
            store=app_context.store,
            llm=LangChainToolsLLM(
                init_chat_model("gemini-2.5-flash", model_provider="google_genai")
            ),
            handoff=LoggingHandoff(),
        )
        # Create a basic agent instance config
        from app.config.provider import AgentInstanceConfig

        agent_instance = AgentInstanceConfig(
            instance_id="default_sales_qualifier", agent_type="sales_qualifier"
        )

    # Build the agent in strict mode to mirror CLI default behavior
    agent = build_sales_qualifier_agent(
        user_id=sender_number or "unknown",
        deps=agent_deps,
        instance=agent_instance,
        strict_mode=True,
    )

    inbound = InboundMessage(
        user_id=sender_number or "unknown", text=message_text, channel="whatsapp", metadata={}
    )

    # Pass tenant_id and project_context via metadata for centralized access
    inbound.metadata["tenant_id"] = str(tenant_id) if tenant_id else "unknown"
    if project_context:
        inbound.metadata["project_context"] = project_context
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

    # Rewrite into multi-message plan with project context for better communication style
    messages = rewriter.rewrite_message(
        reply_text, chat_history, enable_rewrite=True, project_context=project_context
    )
    try:
        plan_preview = [
            f"{int(m.get('delay_ms', 0))}ms: {str(m.get('text', '')).strip()}"
            for m in messages or []
            if isinstance(m, dict)
        ]
        logger.info("WhatsApp message plan (%d): %s", len(messages or []), plan_preview)
    except Exception:
        pass

    # First message is sent synchronously
    first_message = messages[0] if messages else {"text": reply_text, "delay_ms": 0}
    sync_reply = str(first_message.get("text", reply_text)).strip() or reply_text

    logger.info("Sending WhatsApp reply: %r (total messages: %d)", sync_reply, len(messages))

    # Persist chat to SQL using async message logging service for non-blocking operation
    if tenant_id:  # We already have tenant_id from earlier database lookup
        try:
            session = create_session()
            try:
                channel_instance = find_channel_instance_by_identifier(session, receiver_number)
                if channel_instance is not None:
                    # Contact external_id is the full provider id (e.g., whatsapp:+55119...)
                    contact = get_or_create_contact(
                        session,
                        tenant_id,
                        external_id=sender_number,
                        phone_number=sender_number.replace("whatsapp:", ""),
                        display_name=None,
                    )
                    thread = get_or_create_thread(
                        session,
                        tenant_id=tenant_id,
                        channel_instance_id=channel_instance.id,
                        contact_id=contact.id,
                        flow_id=None,
                    )
                    session.commit()  # Commit contact and thread creation synchronously

                    # Log inbound message asynchronously (non-blocking)
                    await message_logging_service.save_message_async(
                        tenant_id=tenant_id,
                        channel_instance_id=channel_instance.id,
                        thread_id=thread.id,
                        contact_id=contact.id,
                        text=message_text,
                        direction=MessageDirection.inbound,
                        provider_message_id=params.get("SmsMessageSid") or params.get("MessageSid"),
                        status=MessageStatus.delivered,
                        delivered_at=datetime.now(UTC),
                    )

                    # Log outbound sync reply asynchronously (non-blocking)
                    if sync_reply:
                        await message_logging_service.save_message_async(
                            tenant_id=tenant_id,
                            channel_instance_id=channel_instance.id,
                            thread_id=thread.id,
                            contact_id=contact.id,
                            text=sync_reply,
                            direction=MessageDirection.outbound,
                            status=MessageStatus.sent,
                            sent_at=datetime.now(UTC),
                        )

            finally:
                session.close()
        except Exception as exc:  # pragma: no cover - best effort persistence
            logger.warning("Failed to persist WhatsApp chat metadata: %s", exc)

    # Send follow-ups if there are any
    if len(messages) > 1:
        try:
            adapter.send_followups(sender_number, receiver_number, messages)
        except Exception as e:
            logger.warning("Failed to send WhatsApp follow-ups: %s", e)

    return adapter.build_sync_response(sync_reply)
