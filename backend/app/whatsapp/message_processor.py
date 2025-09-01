"""Clean WhatsApp message processor with proper loose coupling.

This processor handles only WhatsApp-specific concerns and uses dependency injection
to achieve loose coupling with the flow processing engine. It follows FAANG-level
engineering practices for clean, maintainable code.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import Request, Response
from fastapi.responses import PlainTextResponse

from app.core.app_context import get_app_context
from app.core.channel_adapter import ConversationalRewriter
from app.core.flow_processor import FlowProcessingResult, FlowProcessor, FlowRequest
from app.db.models import MessageDirection, MessageStatus
from app.services.deduplication_service import MessageDeduplicationService
from app.services.message_logging_service import message_logging_service
from app.services.session_manager import RedisSessionManager
from app.settings import get_settings
from app.whatsapp.thread_status_updater import WhatsAppThreadStatusUpdater
from app.whatsapp.webhook_db_handler import WebhookDatabaseHandler

if TYPE_CHECKING:
    from app.whatsapp.adapter import WhatsAppAdapter

logger = logging.getLogger(__name__)


class WhatsAppMessageProcessor:
    """
    WhatsApp message processor with clean architecture.
    
    Responsibilities:
    - WhatsApp message parsing and validation
    - WhatsApp typing indicators
    - WhatsApp-specific deduplication
    - WhatsApp response formatting and delivery
    - WhatsApp message logging
    - Coordinating with flow processor via dependency injection
    """

    MAX_INPUT_CHARS = 500

    def __init__(self, adapter: WhatsAppAdapter):
        self.adapter = adapter
        self.settings = get_settings()

    async def process_message(
        self,
        request: Request,
        x_twilio_signature: str | None
    ) -> Response:
        """
        Process incoming WhatsApp message.
        
        This method handles all WhatsApp-specific operations and coordinates
        with the flow processor for business logic processing.
        """
        # Step 1: Parse WhatsApp webhook (adapter will raise HTTPException for invalid signatures)
        params = await self.adapter.validate_and_parse(request, x_twilio_signature)

        app_context = get_app_context(request.app)  # type: ignore[arg-type]

        # Step 2: Extract WhatsApp message data
        message_data = self._extract_whatsapp_message_data(params, request)

        # Skip processing if no meaningful message content (delivery receipts, status updates, etc.)
        if not message_data.get("sender_number") or not message_data.get("receiver_number"):
            logger.info("WhatsApp webhook received but no sender/receiver - likely delivery receipt or status update")
            return PlainTextResponse("ok")

        # Step 3: Check WhatsApp-specific duplicates
        if self._is_duplicate_whatsapp_message(message_data, app_context):
            logger.debug("WhatsApp message %s from %s is duplicate - already processed",
                        message_data.get("message_id", "unknown"), message_data.get("sender_number", "unknown"))
            return PlainTextResponse("ok")

        # Step 4: Send WhatsApp typing indicator
        await self._send_whatsapp_typing_indicator(message_data)

        # Step 5: Setup conversation context
        conversation_setup = self._setup_conversation_context(message_data)
        if not conversation_setup:
            return self.adapter.build_sync_response(
                "Desculpe, este número do WhatsApp não está configurado."
            )

        # Step 6: Process through flow processor with dependency injection
        flow_response = await self._process_through_flow_processor(
            message_data, conversation_setup, app_context
        )

        # Step 7: Build WhatsApp response
        return await self._build_whatsapp_response(
            flow_response, message_data, conversation_setup, app_context
        )

    def _extract_whatsapp_message_data(
        self,
        params: dict[str, Any],
        request: Request
    ) -> dict[str, Any] | None:
        """Extract WhatsApp-specific message data."""
        sender_number = params.get("From", "")
        receiver_number = params.get("To", "")
        message_text = params.get("Body", "")

        # Extract WhatsApp message ID
        message_id = (
            params.get("MessageSid") or
            params.get("SmsMessageSid") or
            params.get("message_id") or
            # WhatsApp Cloud API format
            (params.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0].get("id")
             if isinstance(params.get("entry"), list) else None)
        )

        client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")

        # Apply WhatsApp message length limits
        if len(message_text) > self.MAX_INPUT_CHARS:
            message_text = message_text[:self.MAX_INPUT_CHARS]

        logger.info(
            "Incoming WhatsApp message from %s to %s: %s",
            sender_number, receiver_number, message_text
        )

        return {
            "sender_number": sender_number,
            "receiver_number": receiver_number,
            "message_text": message_text,
            "message_id": message_id,
            "client_ip": client_ip,
            "params": params,
        }

    def _is_duplicate_whatsapp_message(
        self,
        message_data: dict[str, Any],
        app_context: Any
    ) -> bool:
        """Check for WhatsApp-specific duplicate messages."""
        dedup_service = MessageDeduplicationService(app_context.store)
        return dedup_service.is_duplicate_message(
            message_data["message_id"],
            message_data["sender_number"],
            message_data["receiver_number"],
            message_data["params"],
            message_data["client_ip"]
        )

    async def _send_whatsapp_typing_indicator(self, message_data: dict[str, Any]) -> None:
        """Send WhatsApp typing indicator."""
        if (self.settings.whatsapp_provider == "cloud_api" and
            message_data["message_id"] and
            hasattr(self.adapter, "send_typing_indicator")):

            try:
                await asyncio.sleep(1.0)

                clean_to = message_data["sender_number"].replace("whatsapp:", "")
                clean_from = message_data["receiver_number"].replace("whatsapp:", "")

                self.adapter.send_typing_indicator(clean_to, clean_from, message_data["message_id"])  # type: ignore[attr-defined]
                logger.debug("Sent WhatsApp typing indicator for message %s", message_data["message_id"])
            except Exception as e:
                logger.warning("Failed to send WhatsApp typing indicator: %s", e)

    def _setup_conversation_context(self, message_data: dict[str, Any]):
        """Setup conversation context."""
        try:
            from app.db.session import db_transaction
            with db_transaction() as session:
                db_handler = WebhookDatabaseHandler(session)
                return db_handler.setup_conversation(
                    message_data["sender_number"],
                    message_data["receiver_number"]
                )
        except Exception as e:
            logger.error("Failed to setup WhatsApp conversation context: %s", e)
            return None

    async def _process_through_flow_processor(
        self,
        message_data: dict[str, Any],
        conversation_setup: Any,
        app_context: Any
    ):
        """Process through the flow processor with dependency injection."""
        # Create flow request
        flow_request = FlowRequest(
            user_id=message_data["sender_number"],
            user_message=message_data["message_text"],
            flow_definition=conversation_setup.flow_definition,
            flow_metadata={
                "flow_name": conversation_setup.flow_name,
                "flow_id": conversation_setup.flow_id,
                "thread_id": conversation_setup.thread_id,
                "selected_flow_id": conversation_setup.selected_flow_id,
            },
            tenant_id=conversation_setup.tenant_id,
            project_context=conversation_setup.project_context,
            channel_id=message_data["receiver_number"],  # WhatsApp business number for customer traceability
        )

        # Create dependencies with dependency injection
        session_manager = RedisSessionManager(app_context.store)
        thread_updater = WhatsAppThreadStatusUpdater()

        # Create flow processor with injected dependencies
        flow_processor = FlowProcessor(
            llm=app_context.llm,
            session_manager=session_manager,
            training_handler=None,
            thread_updater=thread_updater,
        )

        # Process through flow processor
        return await flow_processor.process_flow(flow_request, app_context)

    async def _build_whatsapp_response(
        self,
        flow_response,
        message_data: dict[str, Any],
        conversation_setup: Any,
        app_context: Any,
    ) -> Response:
        """Build WhatsApp-specific response."""
        # Handle flow processor errors
        if not flow_response.is_success:
            logger.error("Flow processor error for user %s: %s",
                        message_data["sender_number"], flow_response.error)
            return self.adapter.build_sync_response(
                "Desculpe, erro interno do sistema. Tente novamente."
            )

        # Determine reply text
        if flow_response.result == FlowProcessingResult.ESCALATE:
            reply_text = flow_response.message or "Vou chamar alguém para ajudar você."
            logger.warning("Flow escalated for tenant %s: %s",
                          conversation_setup.tenant_id, reply_text)
        elif flow_response.result == FlowProcessingResult.TERMINAL:
            reply_text = flow_response.message or "Obrigado pela conversa!"
            logger.info("Flow completed for tenant %s: %s",
                       conversation_setup.tenant_id, reply_text)
        else:
            reply_text = flow_response.message or ""

        # Apply WhatsApp message rewriting
        messages = self._rewrite_for_whatsapp(
            reply_text, flow_response, message_data, conversation_setup, app_context
        )

        # Extract sync response
        first_message = messages[0] if messages else {"text": reply_text, "delay_ms": 0}
        sync_reply = str(first_message.get("text", reply_text)).strip() or reply_text

        logger.info("Sending WhatsApp reply: %r (total messages: %d)", sync_reply, len(messages))

        # Log WhatsApp messages
        await self._log_whatsapp_messages(message_data, conversation_setup, sync_reply)

        # Send WhatsApp follow-ups
        if len(messages) > 1:
            await self._send_whatsapp_followups(message_data, messages, app_context)

        return self.adapter.build_sync_response(sync_reply)

    def _rewrite_for_whatsapp(
        self,
        reply_text: str,
        flow_response,
        message_data: dict[str, Any],
        conversation_setup: Any,
        app_context: Any,
    ) -> list[dict[str, Any]]:
        """Apply WhatsApp-specific message rewriting."""
        rewriter = ConversationalRewriter(getattr(app_context, "llm", None))

        chat_history = rewriter.build_chat_history(
            flow_context_history=getattr(flow_response.context, "history", None) if flow_response.context else None,
            latest_user_input=message_data["message_text"]
        )

        print(f"[DEBUG WHATSAPP] About to rewrite message: '{reply_text[:100]}...'")
        print(f"[DEBUG WHATSAPP] Flow response metadata: {getattr(flow_response, 'metadata', {})}")

        # Check if this is an admin operation that shouldn't be rewritten
        metadata = getattr(flow_response, "metadata", {})
        is_admin_operation = (
            metadata.get("tool_name") == "ModifyFlowLive" or
            metadata.get("flow_modified") == True or
            "admin" in reply_text.lower() or
            "instrução" in reply_text.lower()
        )

        print(f"[DEBUG WHATSAPP] Is admin operation: {is_admin_operation}")

        # Skip rewriting for admin operations to preserve the technical message
        if is_admin_operation:
            print("[DEBUG WHATSAPP] Skipping rewrite for admin operation")
            messages = [{"text": reply_text, "delay_ms": 0}]
        else:
            messages = rewriter.rewrite_message(
                reply_text,
                chat_history,
                enable_rewrite=True,
                project_context=conversation_setup.project_context,
                is_completion=(flow_response.result == FlowProcessingResult.TERMINAL)
            )

        print(f"[DEBUG WHATSAPP] Rewriter returned {len(messages or [])} messages")

        # Log WhatsApp message plan
        try:
            plan_preview = [
                f"{int(m.get('delay_ms', 0))}ms: {str(m.get('text', '')).strip()}"
                for m in messages or []
                if isinstance(m, dict)
            ]
            logger.info("WhatsApp message plan (%d): %s", len(messages or []), plan_preview)
        except Exception:
            pass

        return messages or [{"text": reply_text, "delay_ms": 0}]

    async def _log_whatsapp_messages(
        self,
        message_data: dict[str, Any],
        conversation_setup: Any,
        sync_reply: str
    ) -> None:
        """Log WhatsApp messages asynchronously."""
        try:
            # Log inbound message
            await message_logging_service.save_message_async(
                tenant_id=conversation_setup.tenant_id,
                channel_instance_id=conversation_setup.channel_instance_id,
                thread_id=conversation_setup.thread_id,
                contact_id=conversation_setup.contact_id,
                text=message_data["message_text"],
                direction=MessageDirection.inbound,
                provider_message_id=(
                    message_data["params"].get("SmsMessageSid") or
                    message_data["params"].get("MessageSid")
                ),
                status=MessageStatus.delivered,
                delivered_at=datetime.now(UTC),
            )

            # Log outbound reply
            if sync_reply:
                await message_logging_service.save_message_async(
                    tenant_id=conversation_setup.tenant_id,
                    channel_instance_id=conversation_setup.channel_instance_id,
                    thread_id=conversation_setup.thread_id,
                    contact_id=conversation_setup.contact_id,
                    text=sync_reply,
                    direction=MessageDirection.outbound,
                    status=MessageStatus.sent,
                    sent_at=datetime.now(UTC),
                )
        except Exception as exc:
            logger.warning("Failed to log WhatsApp messages: %s", exc)

    async def _send_whatsapp_followups(
        self,
        message_data: dict[str, Any],
        messages: list[dict[str, Any]],
        app_context: Any,
    ) -> None:
        """Send WhatsApp follow-up messages."""
        try:
            from uuid import uuid4
            reply_id = str(uuid4())

            from app.core.redis_keys import redis_keys
            current_reply_key = redis_keys.current_reply_key(message_data["sender_number"])
            # Extract the key part after "chatai:state:system:" for the store.save call
            key_suffix = current_reply_key.replace("chatai:state:system:", "")
            app_context.store.save("system", key_suffix, {
                "reply_id": reply_id,
                "timestamp": int(datetime.now().timestamp())
            })

            self.adapter.send_followups(
                message_data["sender_number"],
                message_data["receiver_number"],
                messages,
                reply_id,
                app_context.store
            )
        except Exception as e:
            logger.warning("Failed to send WhatsApp follow-ups: %s", e)
