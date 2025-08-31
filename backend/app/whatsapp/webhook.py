"""WhatsApp webhook handler with training mode support."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse

from app.core.app_context import get_app_context
from app.core.channel_adapter import ConversationalRewriter
from app.core.state import RedisStore
from app.core.thought_tracer import ThoughtTracer
from app.db.models import MessageDirection, MessageStatus, ThreadStatus
from app.db.repository import (
    find_channel_instance_by_identifier,
    get_flows_by_channel_instance,
    get_or_create_contact,
    get_or_create_thread,
)
from app.db.session import create_session
from app.flow_core.compiler import compile_flow
from app.flow_core.ir import Flow
from app.flow_core.runner import FlowTurnRunner
from app.flow_core.state import FlowContext
from app.flow_core.tool_schemas import EnterTrainingMode
from app.services.message_logging_service import message_logging_service
from app.services.tenant_config_service import TenantConfigService
from app.services.training_mode_service import TrainingModeService
from app.settings import get_settings

if TYPE_CHECKING:
    from .adapter import WhatsAppAdapter

from .twilio_adapter import TwilioWhatsAppAdapter
from .whatsapp_api_adapter import WhatsAppApiAdapter

logger = logging.getLogger(__name__)


def _get_adapter(settings: Any, *, use_whatsapp_api: bool = False) -> WhatsAppAdapter:  # type: ignore[type-arg]
    """Get the appropriate WhatsApp adapter based on configuration."""
    if use_whatsapp_api:
        return WhatsAppApiAdapter(settings)
    return TwilioWhatsAppAdapter(settings)


async def handle_twilio_whatsapp_webhook(
    request: Request, x_twilio_signature: str | None
) -> Response:
    """Database-driven webhook implementation - no hardcoded agents or configs."""
    # Validation is delegated to adapter; keep header presence check minimal
    if not x_twilio_signature:
        # Adapter will raise HTTP 400 if required; but allow test monkeypatch to proceed
        pass

    settings = get_settings()
    use_whatsapp_api = settings.whatsapp_provider == "cloud_api"
    adapter = _get_adapter(settings, use_whatsapp_api=use_whatsapp_api)

    params = await adapter.validate_and_parse(request, x_twilio_signature)
    if not params:
        return PlainTextResponse("ok")

    app_context = get_app_context(request.app)  # type: ignore[arg-type]

    # Extract basic message info upfront for deduplication
    sender_number = params.get("From", "")
    receiver_number = params.get("To", "")
    message_text = params.get("Body", "")

    # Get message ID for deduplication (support both Twilio and WhatsApp Cloud API formats)
    message_id = (
        params.get("MessageSid") or
        params.get("SmsMessageSid") or
        params.get("message_id") or
        # For WhatsApp Cloud API webhook format
        (params.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0].get("id") if isinstance(params.get("entry"), list) else None)
    )
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")

    if message_id:
        logger.debug("Processing webhook with message_id=%s from IP=%s", message_id, client_ip)
        # Check if we've already processed this message (with TTL check)
        dedup_key = f"webhook_processed:{message_id}"
        existing = app_context.store.load("system", dedup_key)
        if existing and isinstance(existing, dict):
            processed_at = existing.get("processed_at", 0)
            # If processed within last 5 minutes, skip
            DEDUP_TTL_SECONDS = 300
            if time.time() - processed_at < DEDUP_TTL_SECONDS:
                logger.info("Skipping duplicate webhook for message_id=%s from IP=%s (processed %ds ago)",
                           message_id, client_ip, int(time.time() - processed_at))
                return PlainTextResponse("ok")

        # Mark message as being processed
        app_context.store.save("system", dedup_key, {"processed_at": int(time.time())})
        logger.debug("Marked message %s as processed for deduplication", message_id)
    else:
        logger.warning("No message ID found for deduplication in webhook from IP=%s, params keys: %s",
                      client_ip, list(params.keys()))
        # For webhooks without message IDs (like status updates), use a combination of other fields for deduplication
        fallback_key = f"{sender_number}:{receiver_number}:{hash(str(params))}"
        dedup_key = f"webhook_processed:{fallback_key}"
        existing = app_context.store.load("system", dedup_key)
        if existing and isinstance(existing, dict):
            processed_at = existing.get("processed_at", 0)
            # Shorter TTL for fallback deduplication
            FALLBACK_DEDUP_TTL_SECONDS = 30
            if time.time() - processed_at < FALLBACK_DEDUP_TTL_SECONDS:
                logger.info("Skipping likely duplicate webhook (no message_id) from IP=%s (processed %ds ago)",
                           client_ip, int(time.time() - processed_at))
                return PlainTextResponse("ok")

        # Mark as processed with shorter TTL
        app_context.store.save("system", dedup_key, {"processed_at": int(time.time())})

    # Generate unique reply ID for this conversation turn to handle interruptions
    reply_id = str(uuid4())

    # Update current reply ID for this user to cancel any pending follow-ups
    current_reply_key = f"current_reply:{sender_number}"
    app_context.store.save("system", current_reply_key, {"reply_id": reply_id, "timestamp": int(time.time())})
    logger.debug("Set current reply ID %s for user %s", reply_id, sender_number)

    MAX_INPUT_CHARS = 500
    if len(message_text) > MAX_INPUT_CHARS:
        message_text = message_text[:MAX_INPUT_CHARS]
    logger.info(
        "Incoming WhatsApp message from %s to %s: %s", sender_number, receiver_number, message_text
    )

    # Send typing indicator immediately for WhatsApp Cloud API (only if we have a message_id)
    # This gives users immediate feedback that their message was received and is being processed
    if settings.whatsapp_provider == "cloud_api" and message_id and isinstance(adapter, WhatsAppApiAdapter):
        try:
            # Extract clean phone numbers for typing indicator
            clean_to = sender_number.replace("whatsapp:", "")
            clean_from = receiver_number.replace("whatsapp:", "")
            adapter.send_typing_indicator(clean_to, clean_from, message_id)
            logger.debug("Sent typing indicator for message %s from %s", message_id, sender_number)
        except Exception as e:
            logger.warning("Failed to send typing indicator: %s", e)
            # Continue processing even if typing indicator fails

    # PRODUCTION SAFETY: Use single database session for entire webhook processing
    # This prevents race conditions and ensures transactional consistency
    main_session = create_session()
    project_context = None
    tenant_id: UUID | None = None

    try:
        # Step 1: Get tenant configuration
        tenant_service = TenantConfigService(main_session)
        project_context = tenant_service.get_project_context_by_channel_identifier(receiver_number)

        if not project_context:
            logger.warning("No tenant configuration found for WhatsApp number: %s", receiver_number)
            return adapter.build_sync_response(
                "Desculpe, este número do WhatsApp não está configurado."
            )

        tenant_id = project_context.tenant_id
        logger.info("Found tenant %s for channel %s", tenant_id, receiver_number)

        # Step 2: Get channel instance
        channel_instance = find_channel_instance_by_identifier(main_session, receiver_number)
        if not channel_instance:
            logger.error("No channel instance found for number %s (tenant %s)", receiver_number, tenant_id)
            return adapter.build_sync_response("Desculpe, este número do WhatsApp não está configurado.")

        # Step 3: Ensure contact/thread exist
        contact = get_or_create_contact(
            main_session,
            tenant_id,
            external_id=sender_number,
            phone_number=sender_number.replace("whatsapp:", ""),
            display_name=None,
        )
        thread = get_or_create_thread(
            main_session,
            tenant_id=tenant_id,
            channel_instance_id=channel_instance.id,
            contact_id=contact.id,
            flow_id=None,
        )

        # Commit the basic setup
        main_session.commit()

        # Step 4: Get flows specifically for this channel instance
        flows = get_flows_by_channel_instance(main_session, channel_instance.id)
        if not flows:
            logger.error("No flows found for channel instance %s (tenant %s)", channel_instance.id, tenant_id)
            return adapter.build_sync_response("Desculpe, nenhum fluxo configurado para este número.")

        # Select first active flow for this specific channel
        active_flows = [f for f in flows if f.is_active]
        if not active_flows:
            logger.error("No active flows found for channel instance %s (tenant %s)", channel_instance.id, tenant_id)
            return adapter.build_sync_response("Desculpe, nenhum fluxo ativo disponível.")

        selected_flow = active_flows[0]
        logger.info("Using flow '%s' (flow_id='%s') for tenant %s",
                   selected_flow.name, selected_flow.flow_id, tenant_id)

        # Load and compile flow definition
        flow_data = selected_flow.definition
        if isinstance(flow_data, dict) and flow_data.get("schema_version") != "v2":
            flow_data["schema_version"] = "v2"

        flow = Flow.model_validate(flow_data)
        compiled_flow = compile_flow(flow)

        # Create thought tracer if Redis is available
        thought_tracer = None
        if isinstance(app_context.store, RedisStore):
            thought_tracer = ThoughtTracer(app_context.store)

        # Create tool event handler for training mode
        def on_tool_event(tool_name: str, metadata: dict[str, Any]) -> bool:
            if tool_name == "EnterTrainingMode":
                # Handle training mode entry via callback
                training = TrainingModeService(main_session, app_context)
                prompt = training.start_handshake(
                    thread,
                    selected_flow,
                    user_id=sender_number,
                    flow_session_key=flow_session_id,
                )
                # Clear any existing flow context to avoid interference
                try:
                    app_context.store.save(sender_number, flow_session_id, {})
                except Exception:
                    pass
                # Store prompt for response (callback can't return response directly)
                setattr(app_context, "_training_prompt", prompt)
                return True  # Signal interception
            return False  # Let engine handle other tools

        # Create flow runner (database-driven, not hardcoded)
        runner = FlowTurnRunner(
            compiled_flow=compiled_flow,
            llm=app_context.llm,
            strict_mode=True,  # Mirror CLI behavior
            thought_tracer=thought_tracer,
            extra_tools=[EnterTrainingMode],
            instruction_prefix=(
                "IMPORTANT: You may ONLY call EnterTrainingMode when the user explicitly mentions\n"
                "phrases like 'modo teste', 'modo treino', 'ativar modo de treinamento', or clear\n"
                "equivalents in Portuguese. Do NOT infer or guess. If not explicit, do NOT call it."
            ),
            on_tool_event=on_tool_event,
        )

        logger.info("Flow runner initialized for tenant %s with flow %s", tenant_id, flow.id)

    except Exception as e:
        logger.error("Failed to process webhook for tenant %s: %s", tenant_id, e)
        # Rollback any pending changes
        try:
            main_session.rollback()
        except Exception:
            pass
        return adapter.build_sync_response("Desculpe, erro interno do sistema. Tente novamente.")
    finally:
        # Always close the main database session
        try:
            main_session.close()
        except Exception as e:
            logger.warning("Failed to close main database session: %s", e)

    # Use distributed locking to prevent concurrent processing of the same user's flow
    flow_session_id = f"flow:{sender_number}:{selected_flow.flow_id}"
    lock_key = f"lock:{flow_session_id}"

    # Try to acquire lock with timeout
    LOCK_WAIT_SECONDS = 30
    LOCK_HOLD_SECONDS = 60
    lock_acquired = False
    lock_expiry = int(time.time()) + LOCK_HOLD_SECONDS

    try:
        # Simple Redis-based distributed lock
        for attempt in range(LOCK_WAIT_SECONDS):
            if hasattr(app_context.store, "_r"):  # Redis store
                # Try to set lock with expiry
                current_time = int(time.time())
                lock_set = app_context.store._r.set(lock_key, lock_expiry, nx=True, ex=LOCK_HOLD_SECONDS)
                if lock_set:
                    lock_acquired = True
                    logger.debug("Acquired lock for %s", flow_session_id)
                    break

                # Check if existing lock has expired
                existing_lock = app_context.store._r.get(lock_key)
                if existing_lock:
                    try:
                        existing_expiry = int(existing_lock.decode() if isinstance(existing_lock, bytes) else existing_lock)
                        if current_time > existing_expiry:
                            # Lock expired, try to claim it
                            if app_context.store._r.getset(lock_key, lock_expiry):
                                lock_acquired = True
                                logger.debug("Claimed expired lock for %s", flow_session_id)
                                break
                    except (ValueError, TypeError):
                        pass
            else:
                # Fallback for non-Redis stores - just proceed
                lock_acquired = True
                break

            if attempt < LOCK_WAIT_SECONDS - 1:  # Don't sleep on last attempt
                time.sleep(1)

        if not lock_acquired:
            logger.warning("Failed to acquire lock for %s, proceeding anyway", flow_session_id)

        # Initialize or retrieve flow context from session storage
        existing_context_data = app_context.store.load(sender_number, flow_session_id)

        existing_context = None
        if existing_context_data and isinstance(existing_context_data, dict):
            try:
                existing_context = FlowContext.from_dict(existing_context_data)
                logger.debug("Loaded existing flow context for session %s", flow_session_id)
            except Exception as e:
                logger.warning("Failed to deserialize flow context, creating new: %s", e)

        ctx = runner.initialize_context(existing_context)

        # If user is in the middle of entering training password, short-circuit here
        training = TrainingModeService(main_session, app_context)
        if training.awaiting_password(thread, user_id=sender_number):
            handled, reply = training.validate_password(
                thread,
                selected_flow,
                message_text,
                user_id=sender_number,
                flow_session_key=flow_session_id,
            )
            return adapter.build_sync_response(reply)

        # If training mode is active, route to flow modification system
        if getattr(thread, "training_mode", False):
            try:
                reply_text = await training.handle_training_message(
                    thread, selected_flow, message_text, project_context
                )
            except Exception as e:
                logger.error("Training mode processing failed: %s", e)
                reply_text = "Falha ao processar instrução de treino. Tente novamente."
            return adapter.build_sync_response(reply_text)

        # Process the user message through the flow
        result = runner.process_turn(
            ctx=ctx,
            user_message=message_text,
            project_context=project_context
        )

        # Handle tool event interception via callback
        if result.tool_name == "EnterTrainingMode":
            prompt = getattr(app_context, "_training_prompt", "Para entrar no modo treino, informe a senha.")
            # Clean up temporary attribute
            if hasattr(app_context, "_training_prompt"):
                delattr(app_context, "_training_prompt")
            return adapter.build_sync_response(prompt)

        # Handle flow result
        if result.escalate:
            logger.warning("Flow escalated for tenant %s: %s", tenant_id, result.assistant_message)
            reply_text = result.assistant_message or "Vou chamar alguém para ajudar você."
        elif result.terminal:
            logger.info("Flow completed for tenant %s: %s", tenant_id, result.assistant_message)
            reply_text = result.assistant_message or "Obrigado pela conversa!"
            # Clear context on completion
            try:
                app_context.store.save(sender_number, flow_session_id, {})
                logger.debug("Cleared flow context on completion")
            except Exception as e:
                logger.warning("Failed to clear completed flow context: %s", e)
        else:
            reply_text = result.assistant_message or ""

        # Update ChatThread with flow completion or escalation data
        if result.escalate or result.terminal:
            try:
                # We already have channel_instance, contact, thread from main_session
                # Just update the existing thread object

                if result.escalate:
                    # Track human handoff request
                    thread.human_handoff_requested_at = datetime.now(UTC)
                    logger.info("Marked thread %s for human handoff", thread.id)

                if result.terminal:
                    # Store completion data and close thread
                    thread.flow_completion_data = {
                        "answers": ctx.answers,
                        "flow_id": selected_flow.flow_id,
                        "flow_name": selected_flow.name,
                        "completion_message": result.assistant_message,
                        "total_messages": len(getattr(ctx, "history", [])),
                    }
                    thread.completed_at = datetime.now(UTC)
                    thread.status = ThreadStatus.closed
                    logger.info("Closed thread %s with completion data", thread.id)

                main_session.commit()
            except Exception as e:
                logger.error("Failed to update thread with flow result: %s", e)
                main_session.rollback()

        # Store updated context back to session storage for next turn
        if not result.terminal:  # Only save if conversation is continuing
            try:
                app_context.store.save(sender_number, flow_session_id, result.ctx.to_dict())
                logger.debug("Saved updated flow context for session %s", flow_session_id)
            except Exception as e:
                logger.error("Failed to save flow context: %s", e)

    finally:
        # Always release the lock
        if lock_acquired and hasattr(app_context.store, "_r"):
            try:
                # Only delete if we still own the lock (check expiry)
                current_lock = app_context.store._r.get(lock_key)
                if current_lock:
                    try:
                        current_expiry = int(current_lock.decode() if isinstance(current_lock, bytes) else current_lock)
                        if current_expiry == lock_expiry:  # We still own this lock
                            app_context.store._r.delete(lock_key)
                            logger.debug("Released lock for %s", flow_session_id)
                    except (ValueError, TypeError):
                        # If we can't parse, just delete anyway
                        app_context.store._r.delete(lock_key)
            except Exception as e:
                logger.warning("Failed to release lock for %s: %s", flow_session_id, e)

    # Setup rewriter with app context LLM
    rewriter = ConversationalRewriter(getattr(app_context, "llm", None))

    # Build chat history from flow context
    chat_history = rewriter.build_chat_history(
        flow_context_history=getattr(ctx, "history", None),
        latest_user_input=message_text
    )

    # Rewrite into multi-message plan with project context for better communication style
    messages = rewriter.rewrite_message(
        reply_text, chat_history, enable_rewrite=True, project_context=project_context, is_completion=result.terminal
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
    if tenant_id and "channel_instance" in locals() and "thread" in locals() and "contact" in locals():
        try:
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
        except Exception as exc:  # pragma: no cover - best effort persistence
            logger.warning("Failed to persist WhatsApp chat metadata: %s", exc)

    # Send follow-ups if there are any
    if len(messages) > 1:
        try:
            adapter.send_followups(sender_number, receiver_number, messages, reply_id, app_context.store)
        except Exception as e:
            logger.warning("Failed to send WhatsApp follow-ups: %s", e)

    return adapter.build_sync_response(sync_reply)


async def handle_whatsapp_webhook_verification(
    request: Request, hub_mode: str, hub_challenge: str, hub_verify_token: str
) -> Response:
    """Handle WhatsApp webhook verification for Cloud API."""

    settings = get_settings()

    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("WhatsApp webhook verified successfully")
        return PlainTextResponse(hub_challenge, status_code=200)
    else:
        logger.warning("WhatsApp webhook verification failed: mode=%s, token_valid=%s",
                      hub_mode, hub_verify_token == settings.whatsapp_verify_token)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed")