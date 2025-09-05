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
from app.core.flow_processor import FlowProcessingResult, FlowProcessor, FlowRequest
from app.db.models import MessageDirection, MessageStatus
from app.services.deduplication_service import MessageDeduplicationService
from app.services.message_logging_service import message_logging_service
from app.services.processing_cancellation_manager import ProcessingCancelledException
from app.services.session_manager import RedisSessionManager
from app.settings import get_settings
from app.services.speech_to_text_service import SpeechToTextService
from app.services.processing_cancellation_manager import ProcessingCancellationManager
from app.services.audio_validation_service import AudioValidationService
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
        message_data = await self._extract_whatsapp_message_data(params, request)

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

    async def _extract_whatsapp_message_data(
        self,
        params: dict[str, Any],
        request: Request
    ) -> dict[str, Any] | None:
        """Extract WhatsApp-specific message data."""
        sender_number = params.get("From", "")
        receiver_number = params.get("To", "")
        message_text = params.get("Body", "")

        # Handle audio messages early by validating duration and transcribing them to text
        # Check for audio messages more robustly - either empty text or MessageType is audio
        is_audio_message = (
            params.get("MessageType") == "audio" or
            (not message_text and params.get("MessageType") == "audio") or
            (message_text == "[audio message]")  # Fallback for legacy behavior
        )
        
        if is_audio_message:
            stt_service = SpeechToTextService(self.settings)
            audio_validator = AudioValidationService(self.settings.max_audio_duration_seconds)
            
            try:
                num_media = int(str(params.get("NumMedia", "0")) or 0)
                media_type = str(params.get("MediaContentType0", ""))
                media_url = params.get("MediaUrl0")
                
                if (
                    num_media > 0
                    and media_url
                    and media_type.startswith("audio")
                ):
                    # This is legacy Twilio code - transcribe directly since we use WhatsApp Cloud API
                    message_text = await asyncio.to_thread(
                        stt_service.transcribe_twilio_media, media_url
                    )
                        
                elif params.get("MessageType") == "audio":
                    raw_msg = params.get("WhatsAppRawMessage", {})
                    media_id = (
                        raw_msg.get("audio", {}).get("id")
                        if isinstance(raw_msg, dict)
                        else None
                    )
                    if media_id:
                        # Validate WhatsApp API audio duration first
                        is_valid, duration, error_msg = await asyncio.to_thread(
                            audio_validator.validate_whatsapp_api_media_duration,
                            media_id, self.settings.whatsapp_access_token
                        )

                        if not is_valid:
                            logger.info("Audio duration validation failed for WhatsApp API media: %s (duration: %ss)",
                                      error_msg, duration)
                            
                            # Different messages based on whether we could determine duration
                            if duration is not None:
                                # We know it's too long
                                max_minutes = self.settings.max_audio_duration_seconds // 60
                                duration_minutes = duration / 60
                                message_text = f"Desculpe, áudios devem ter no máximo {max_minutes} minutos. Seu áudio tem {duration_minutes:.1f} minutos."
                            else:
                                # Error determining duration
                                message_text = "Estamos com dificuldades para processar áudios no momento. Por favor, envie sua mensagem em texto."
                        else:
                            logger.info("Audio duration validation passed: %.1fs", duration or 0)
                            message_text = await asyncio.to_thread(
                                stt_service.transcribe_whatsapp_api_media, media_id
                            )
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to process WhatsApp audio: %s", e)
                message_text = "[audio message]"

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
        # Build session ID for cancellation coordination  
        session_id = self._build_session_id(
            message_data["sender_number"],
            conversation_setup.flow_id or "unknown"
        )
        
        logger.debug(f"Processing message for session {session_id}: {message_data.get('message_text', '')[:100]}")
        
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
        # Note: Each request creates its own processor, but they share Redis state via cancellation manager
        flow_processor = FlowProcessor(
            llm=app_context.llm,
            session_manager=session_manager,
            training_handler=None,
            thread_updater=thread_updater,
        )

        # Process through flow processor
        return await flow_processor.process_flow(flow_request, app_context)
    
    def _build_session_id(self, user_id: str, flow_id: str) -> str:
        """Build consistent session ID for cancellation coordination."""
        return f"flow:{user_id}:{flow_id}"

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
            # Check if this was a cancellation (not a real error)
            if flow_response.metadata and flow_response.metadata.get("cancelled"):
                logger.info("Flow processing was cancelled for user %s (rapid messages)",
                           message_data["sender_number"])
                # Don't send error message for cancellations - messages are being aggregated
                return PlainTextResponse("ok")
            
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

        # Check for cancellation before naturalizing
        try:
            cancellation_manager = flow_response.metadata.get("cancellation_manager") if flow_response.metadata else None
            session_id = flow_response.metadata.get("session_id") if flow_response.metadata else None
            
            if cancellation_manager and session_id:
                cancellation_manager.check_cancellation_and_raise(session_id, "naturalizing")
        except ProcessingCancelledException:
            logger.info("Message processing cancelled before naturalization")
            # Mark this cancelled processing as complete
            if cancellation_manager and session_id:
                cancellation_manager.mark_processing_complete(session_id)
            return PlainTextResponse("ok")  # Don't send anything if cancelled

        # Get messages directly from flow response
        messages = self._get_whatsapp_messages(flow_response)

        # Extract sync response
        first_message = messages[0] if messages else {"text": reply_text, "delay_ms": 0}
        sync_reply = str(first_message.get("text", reply_text)).strip() or reply_text

        # Final cancellation check before sending
        try:
            if cancellation_manager and session_id:
                cancellation_manager.check_cancellation_and_raise(session_id, "sending")
        except ProcessingCancelledException:
            logger.info("Message processing cancelled before sending")
            # Mark this cancelled processing as complete
            if cancellation_manager and session_id:
                cancellation_manager.mark_processing_complete(session_id)
            return PlainTextResponse("ok")  # Don't send anything if cancelled

        logger.info("Sending WhatsApp reply: %r (total messages: %d)", sync_reply, len(messages))

        # Log WhatsApp messages
        await self._log_whatsapp_messages(message_data, conversation_setup, sync_reply)

        # Send WhatsApp follow-ups
        if len(messages) > 1:
            await self._send_whatsapp_followups(message_data, messages, app_context)

        # Mark processing complete AFTER message is sent
        # This ensures the cancellation window stays open until the message is actually delivered
        if cancellation_manager and session_id:
            cancellation_manager.mark_processing_complete(session_id)
            logger.debug(f"Marked processing complete for session {session_id}")

        return self.adapter.build_sync_response(sync_reply)

    def _get_whatsapp_messages(
        self,
        flow_response,
    ) -> list[dict[str, Any]]:
        """Get WhatsApp messages from flow response."""
        # Check if flow response has messages
        if hasattr(flow_response, "messages") and flow_response.messages:
            return flow_response.messages
        
        # Fallback to message field
        if hasattr(flow_response, "message") and flow_response.message:
            return [{"text": flow_response.message, "delay_ms": 0}]
        
        # Final fallback
        return [{"text": "Entendi. Vou te ajudar com isso.", "delay_ms": 0}] or
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
            # Build tool context for better naturalization
            tool_context = None
            if metadata.get("tool_name"):
                tool_context = {
                    "tool_name": metadata.get("tool_name", ""),
                    "description": metadata.get("tool_description", ""),
                }
                if metadata.get("ack_message"):
                    tool_context["ack_message"] = metadata.get("ack_message")
            
            # Get current time in same format as conversation timestamps
            import datetime
            current_time = datetime.datetime.now().strftime("%H:%M")
            
            messages = rewriter.rewrite_message(
                reply_text,
                chat_history,
                enable_rewrite=True,
                project_context=conversation_setup.project_context,
                is_completion=(flow_response.result == FlowProcessingResult.TERMINAL),
                tool_context=tool_context,
                current_time=current_time
            )

        print(f"[DEBUG WHATSAPP] Rewriter returned {len(messages or [])} messages")

        # Add naturalized message to flow context history for proper rewriter context
        if messages and flow_response.context:
            try:
                # Combine all rewritten messages into a single string for history
                rewritten_content = " ".join(msg.get("text", "") for msg in messages if msg.get("text"))
                if rewritten_content.strip():
                    # Add to flow context history (which the rewriter uses)
                    flow_response.context.add_turn(
                        "assistant", 
                        rewritten_content,
                        flow_response.context.current_node_id
                    )
                    logger.debug("Added naturalized content to flow context history")
                    
                    # Save the updated context with naturalized message
                    from app.services.session_manager import RedisSessionManager
                    from app.core.redis_keys import RedisKeyBuilder
                    
                    session_manager = RedisSessionManager(app_context.store)
                    user_id = message_data["sender_number"]
                    flow_id = conversation_setup.flow_id
                    
                    # Use the same session ID pattern as RedisSessionManager.create_session()
                    session_id = f"flow:{user_id}:{flow_id}"
                    session_manager.save_context(session_id, flow_response.context)
                    logger.debug("Saved updated context with naturalized history")
                    
                    # Also update Redis/LangChain history for persistence
                    if not is_admin_operation and hasattr(app_context, 'store'):
                        # Use RedisKeyBuilder to create the proper history key
                        key_builder = RedisKeyBuilder(namespace=getattr(app_context.store, '_ns', 'chatai'))
                        
                        if hasattr(app_context.store, 'get_message_history'):
                            history = app_context.store.get_message_history(session_id)
                            if hasattr(history, 'messages') and history.messages:
                                # Update the last assistant message with rewritten content
                                for message in reversed(history.messages):
                                    if hasattr(message, 'type') and message.type == 'ai':
                                        message.content = rewritten_content
                                        break
                            logger.debug("Updated Redis chat history with naturalized content for session %s", session_id)
            except Exception as e:
                logger.warning("Failed to update history with naturalized content: %s", e)

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
