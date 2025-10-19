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

import requests
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse

from app.core.app_context import get_app_context
from app.core.flow_processor import FlowProcessor
from app.core.flow_request import FlowRequest
from app.core.flow_response import FlowProcessingResult
from app.db.models import MessageDirection, MessageStatus
from app.services.audio_validation_service import AudioValidationService
from app.services.deduplication_service import MessageDeduplicationService
from app.services.message_logging_service import message_logging_service
from app.services.processing_cancellation_manager import (
    ProcessingCancelledException,
)
from app.services.session_manager import RedisSessionManager
from app.services.speech_to_text_service import SpeechToTextService
from app.settings import get_settings
from app.whatsapp.thread_status_updater import WhatsAppThreadStatusUpdater
from app.whatsapp.webhook_db_handler import WebhookDatabaseHandler

if TYPE_CHECKING:
    from app.whatsapp.adapter import WhatsAppAdapter

logger = logging.getLogger(__name__)


class WhatsAppMessageProcessor:
    """
    WhatsApp message processor for handling incoming messages.

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

    async def process_message(self, request: Request, x_twilio_signature: str | None) -> Response:
        """
        Process incoming WhatsApp message.

        This method handles all WhatsApp-specific operations and coordinates
        with the flow processor for business logic processing.
        """
        # Step 1: Parse WhatsApp webhook (adapter will raise HTTPException for invalid signatures)
        params = await self.adapter.validate_and_parse(request, x_twilio_signature)

        # Step 1.5: Log raw webhook data for debugging (only in debug/dev mode)
        if self.settings.debug or getattr(self.settings, "environment", "") == "development":
            await self._log_webhook_data(request, params)

        app_context = get_app_context(request.app)  # type: ignore[arg-type]

        # Step 2: Extract WhatsApp message data
        message_data = await self._extract_whatsapp_message_data(params, request)

        # Skip processing if no meaningful message content (delivery receipts, status updates, etc.)
        if not message_data.get("sender_number") or not message_data.get("receiver_number"):
            logger.info(
                "WhatsApp webhook received but no sender/receiver - likely delivery receipt or status update"
            )
            return PlainTextResponse("ok")

        # Step 3: Check WhatsApp-specific duplicates
        if self._is_duplicate_whatsapp_message(message_data, app_context):
            logger.debug(
                "WhatsApp message %s from %s is duplicate - already processed",
                message_data.get("message_id", "unknown"),
                message_data.get("sender_number", "unknown"),
            )
            return PlainTextResponse("ok")

        # Step 4: Send WhatsApp typing indicator
        await self._send_whatsapp_typing_indicator(message_data)

        # Step 5: Setup conversation context
        conversation_setup = self._setup_conversation_context(message_data)
        if not conversation_setup:
            return self.adapter.build_sync_response(
                "Desculpe, este número do WhatsApp não está configurado."
            )

        # Step 6: Get tenant configuration for timing settings
        tenant_config = self._get_tenant_timing_config(conversation_setup)

        # Step 7: Build session ID for message coordination
        session_id = self._build_session_id(
            message_data["sender_number"], conversation_setup.flow_id or "unknown"
        )

        # Step 8: Debounced message handling with aggregation (centralized)
        cancellation_manager = getattr(app_context, "cancellation_manager", None)
        if not cancellation_manager:
            try:
                from app.services.processing_cancellation_manager import ProcessingCancellationManager
                cancellation_manager = ProcessingCancellationManager(store=app_context.store)
            except Exception:
                cancellation_manager = None

        if cancellation_manager and message_data.get("message_text"):
            # Add message to buffer with timestamp
            message_id = cancellation_manager.add_message_to_buffer(
                session_id, message_data["message_text"]
            )
            
            # Wait for the configured delay, checking for new messages periodically
            wait_ms = tenant_config.get("wait_time_before_replying_ms", 60000)
            # Use centralized inactivity waiter
            result = await cancellation_manager.wait_for_inactivity(
                session_id=session_id,
                since_message_id=message_id,
                inactivity_ms=wait_ms,
                check_interval_ms=1000,
            )
            
            if result == "exit":
                # A newer message arrived, let it handle processing
                logger.info(f"Newer message detected for session {session_id}, exiting this webhook")
                return PlainTextResponse("ok")
            elif result == "process_aggregated":
                # Save individual messages to database BEFORE aggregation
                individual_messages = cancellation_manager.get_individual_messages(session_id)
                await self._save_individual_messages(
                    individual_messages, conversation_setup, message_data
                )
                
                # Get aggregated message for LLM processing
                aggregated_message = cancellation_manager.get_and_clear_messages(session_id)
                if aggregated_message:
                    logger.info(
                        f"Processing aggregated messages for {session_id}: {aggregated_message[:100]}..."
                    )
                    message_data["message_text"] = aggregated_message
                    message_data["is_aggregated"] = True
                    message_data["original_message_count"] = len(individual_messages)
                    message_data["skip_inbound_logging"] = True  # Don't log aggregated version
            elif result == "process_single":
                # Single message - will be saved normally
                pass

        # Step 9: Process through flow processor with dependency injection
        flow_response = await self._process_through_flow_processor(
            message_data, conversation_setup, app_context
        )

        # Step 8: Build WhatsApp response
        return await self._build_whatsapp_response(
            flow_response, message_data, conversation_setup, app_context
        )

    async def _extract_whatsapp_message_data(
        self, params: dict[str, Any], request: Request
    ) -> dict[str, Any] | None:
        """Extract WhatsApp-specific message data."""
        sender_number = params.get("From", "")
        receiver_number = params.get("To", "")
        message_text = params.get("Body", "")

        # Handle audio messages early by validating duration and transcribing them to text
        # Check for audio messages more robustly - either empty text or MessageType is audio
        is_audio_message = (
            params.get("MessageType") == "audio"
            or (not message_text and params.get("MessageType") == "audio")
            or (message_text == "[audio message]")  # Fallback for legacy behavior
        )

        logger.debug(
            "Message type check: MessageType=%s, message_text='%s', is_audio=%s",
            params.get("MessageType"),
            message_text[:50] if message_text else "",
            is_audio_message,
        )

        if is_audio_message:
            logger.info("Processing audio message from %s", sender_number)
            stt_service = SpeechToTextService(self.settings)
            audio_validator = AudioValidationService(self.settings.max_audio_duration_seconds)
            logger.debug(
                "Audio validator initialized with max_duration=%ds",
                self.settings.max_audio_duration_seconds,
            )

            try:
                num_media = int(str(params.get("NumMedia", "0")) or 0)
                media_type = str(params.get("MediaContentType0", ""))
                media_url = params.get("MediaUrl0")

                if num_media > 0 and media_url and media_type.startswith("audio"):
                    # Validate Twilio audio duration first
                    is_valid, duration, error_msg = await asyncio.to_thread(
                        audio_validator.validate_twilio_media_duration,
                        media_url,
                        (self.settings.twilio_account_sid, self.settings.twilio_auth_token)
                        if self.settings.twilio_account_sid
                        else None,
                    )

                    if not is_valid:
                        logger.info(
                            "Audio duration validation failed for Twilio media: %s (duration: %ss)",
                            error_msg,
                            duration,
                        )

                        # Pass the audio error to the LLM so it can generate a natural response
                        if duration is not None:
                            # We know it's too long
                            max_minutes = self.settings.max_audio_duration_seconds // 60
                            duration_minutes = duration / 60
                            message_text = f"[AUDIO_ERROR: Áudio muito longo - {duration_minutes:.1f} minutos, máximo permitido {max_minutes} minutos]"
                        else:
                            # Error determining duration or processing
                            message_text = "[AUDIO_ERROR: Não foi possível processar o áudio]"
                    else:
                        logger.info("Audio duration validation passed: %.1fs", duration or 0)
                        transcribed_text = await asyncio.to_thread(
                            stt_service.transcribe_twilio_media, media_url
                        )
                        # Mark that this came from audio for the LLM
                        if transcribed_text:
                            message_text = f"[FROM_AUDIO] {transcribed_text}"
                        else:
                            message_text = transcribed_text

                elif params.get("MessageType") == "audio":
                    raw_msg = params.get("WhatsAppRawMessage", {})
                    media_id = (
                        raw_msg.get("audio", {}).get("id") if isinstance(raw_msg, dict) else None
                    )
                    logger.debug(
                        "WhatsApp Cloud API audio: media_id=%s, raw_msg_keys=%s",
                        media_id,
                        list(raw_msg.keys()) if isinstance(raw_msg, dict) else "not_dict",
                    )

                    if media_id:
                        # Skip duration validation for WhatsApp Cloud API
                        # WhatsApp already limits audio messages and validation requires API token
                        # Just proceed directly to transcription
                        logger.info(
                            "Transcribing WhatsApp audio: media_id=%s (skipping duration validation)",
                            media_id,
                        )
                        try:
                            transcribed_text = await asyncio.to_thread(
                                stt_service.transcribe_whatsapp_api_media, media_id
                            )
                            logger.debug(
                                "Transcription complete: '%s'",
                                transcribed_text[:100] if transcribed_text else "empty",
                            )
                            # Mark that this came from audio for the LLM
                            if transcribed_text:
                                message_text = f"[FROM_AUDIO] {transcribed_text}"
                            else:
                                message_text = transcribed_text
                        except requests.exceptions.HTTPError as e:
                            if e.response and e.response.status_code == 401:
                                logger.error(
                                    "WhatsApp API authentication failed - check WHATSAPP_ACCESS_TOKEN: %s",
                                    e,
                                )
                                message_text = "[AUDIO_ERROR: Configuração do WhatsApp API inválida - verifique o token de acesso]"
                            else:
                                logger.error("HTTP error transcribing WhatsApp audio: %s", e)
                                message_text = "[AUDIO_ERROR: Não foi possível processar o áudio]"
                        except Exception as e:
                            logger.error("Failed to transcribe WhatsApp audio: %s", e)
                            message_text = "[AUDIO_ERROR: Não foi possível processar o áudio]"
                    else:
                        logger.error(
                            "No media_id found in WhatsApp audio message. raw_msg=%s", raw_msg
                        )
                        message_text = (
                            "[AUDIO_ERROR: Não foi possível processar o áudio - ID não encontrado]"
                        )
            except Exception as e:
                logger.error("Failed to process WhatsApp audio: %s", e, exc_info=True)
                message_text = "[AUDIO_ERROR: Erro inesperado ao processar áudio]"

        # Extract WhatsApp message ID
        message_id = (
            params.get("MessageSid")
            or params.get("SmsMessageSid")
            or params.get("message_id")
            or
            # WhatsApp Cloud API format
            (
                params.get("entry", [{}])[0]
                .get("changes", [{}])[0]
                .get("value", {})
                .get("messages", [{}])[0]
                .get("id")
                if isinstance(params.get("entry"), list)
                else None
            )
        )

        client_ip = request.headers.get(
            "x-forwarded-for", request.client.host if request.client else "unknown"
        )

        # Apply WhatsApp message length limits
        if len(message_text) > self.MAX_INPUT_CHARS:
            message_text = message_text[: self.MAX_INPUT_CHARS]

        logger.info(
            "Incoming WhatsApp message from %s to %s: %s",
            sender_number,
            receiver_number,
            message_text,
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
        self, message_data: dict[str, Any], app_context: Any
    ) -> bool:
        """Check for WhatsApp-specific duplicate messages."""
        dedup_service = MessageDeduplicationService(app_context.store)
        return dedup_service.is_duplicate_message(
            message_data["message_id"],
            message_data["sender_number"],
            message_data["receiver_number"],
            message_data["params"],
            message_data["client_ip"],
        )

    async def _log_webhook_data(self, request: Request, params: dict[str, Any]) -> None:
        """Log raw webhook data to file for debugging."""
        try:
            import json
            import os
            from datetime import datetime

            # Create webhook logs directory
            log_dir = "/tmp/webhook-calls"
            os.makedirs(log_dir, exist_ok=True)

            # Get sender number and timestamp
            sender_number = "unknown"
            if "From" in params:
                sender_number = params["From"].replace("whatsapp:", "").replace("+", "")
            elif "entry" in params:  # WhatsApp Cloud API format
                try:
                    entry = params["entry"][0] if params["entry"] else {}
                    changes = entry.get("changes", [{}])[0]
                    messages = changes.get("value", {}).get("messages", [{}])
                    if messages:
                        sender_number = messages[0].get("from", "unknown")
                except (IndexError, KeyError):
                    pass

            # Create timestamp with full precision
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

            # Create filename
            filename = f"{sender_number}_{timestamp}.txt"
            filepath = os.path.join(log_dir, filename)

            # Get request body for logging
            body = await request.body()

            # Prepare log data
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "query_params": dict(request.query_params),
                "parsed_params": params,
                "raw_body": body.decode("utf-8") if body else "",
                "client_ip": request.headers.get(
                    "x-forwarded-for", request.client.host if request.client else "unknown"
                ),
            }

            # Write to file
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            logger.debug(f"[DEBUG MODE] Logged webhook data to {filepath}")

        except Exception as e:
            logger.warning(f"Failed to log webhook data: {e}")

    def _is_likely_retry(self, message_data: dict[str, Any], app_context: Any) -> bool:
        """Check if this is likely a webhook retry based on timing and patterns."""
        # Check if we've recently processed a message from this user
        if not app_context.store or not hasattr(app_context.store, "_r"):
            return False

        try:
            # Create a unique key for this specific message content and sender
            message_text = message_data.get("message_text", "")
            sender = message_data.get("sender_number", "")

            # Use a hash of the message content to handle long messages
            import hashlib

            message_hash = hashlib.md5(message_text.encode()).hexdigest()[:16]

            retry_key = f"webhook_processed:{sender}:{message_hash}"

            # Check if we've seen this exact message recently (within 2 minutes)
            if app_context.store._r.get(retry_key):
                return True

            # Mark this message as processed for 2 minutes (webhook retry window)
            app_context.store._r.setex(retry_key, 120, "1")
            return False
        except Exception as e:
            logger.warning(f"Failed to check retry status: {e}")
            return False

    # Removed: _debounced_wait, use centralized method in ProcessingCancellationManager

    async def _wait_and_send_typing_indicator(
        self, message_data: dict[str, Any], tenant_config: dict[str, Any] | None = None
    ) -> None:
        """Wait before processing and send typing indicator based on tenant config.

        Args:
            message_data: Message information
            tenant_config: Tenant timing configuration
        """
        # Get configuration with defaults
        if tenant_config is None:
            tenant_config = {}

        wait_ms = tenant_config.get("wait_time_before_replying_ms", 60000)
        typing_enabled = tenant_config.get("typing_indicator_enabled", True)
        natural_delays = tenant_config.get("natural_delays_enabled", True)
        variance_percent = tenant_config.get("delay_variance_percent", 20)

        # Add natural variance if enabled
        if natural_delays and variance_percent > 0:
            import secrets

            # Use cryptographically secure random for timing variance
            variance = (secrets.randbelow(2 * variance_percent + 1) - variance_percent) / 100
            wait_ms = int(wait_ms * (1 + variance))

        # Ensure within reasonable bounds (100ms to 2 minutes)
        wait_ms = max(100, min(wait_ms, 120000))

        # Wait for the configured duration
        logger.debug(f"Waiting {wait_ms}ms before processing message")
        await asyncio.sleep(wait_ms / 1000.0)

        # Send typing indicator if enabled
        if (
            typing_enabled
            and self.settings.whatsapp_provider == "cloud_api"
            and message_data["message_id"]
            and hasattr(self.adapter, "send_typing_indicator")
        ):
            try:
                clean_to = message_data["sender_number"].replace("whatsapp:", "")
                clean_from = message_data["receiver_number"].replace("whatsapp:", "")

                self.adapter.send_typing_indicator(clean_to, clean_from, message_data["message_id"])  # type: ignore[attr-defined]
                logger.debug(
                    "Sent WhatsApp typing indicator for message %s", message_data["message_id"]
                )
            except Exception as e:
                logger.warning("Failed to send WhatsApp typing indicator: %s", e)

    def _setup_conversation_context(self, message_data: dict[str, Any]):
        """Setup conversation context."""
        try:
            from app.db.session import db_transaction

            with db_transaction() as session:
                db_handler = WebhookDatabaseHandler(session)
                return db_handler.setup_conversation(
                    message_data["sender_number"], message_data["receiver_number"]
                )
        except Exception as e:
            logger.error("Failed to setup WhatsApp conversation context: %s", e)
            return None

    def _get_tenant_timing_config(self, conversation_setup: Any) -> dict[str, Any]:
        """Get tenant timing configuration from conversation setup.

        Args:
            conversation_setup: ConversationSetup with project_context

        Returns:
            Timing configuration dictionary
        """
        try:
            # Access project_context directly from conversation_setup
            if (
                hasattr(conversation_setup, "project_context")
                and conversation_setup.project_context
            ):
                pc = conversation_setup.project_context
                return {
                    "wait_time_before_replying_ms": getattr(
                        pc, "wait_time_before_replying_ms", 60000
                    ),
                    "typing_indicator_enabled": getattr(pc, "typing_indicator_enabled", True),
                    "min_typing_duration_ms": getattr(pc, "min_typing_duration_ms", 1000),
                    "max_typing_duration_ms": getattr(pc, "max_typing_duration_ms", 5000),
                    "message_reset_enabled": getattr(pc, "message_reset_enabled", True),
                    "natural_delays_enabled": getattr(pc, "natural_delays_enabled", True),
                    "delay_variance_percent": getattr(pc, "delay_variance_percent", 20),
                }
        except Exception as e:
            logger.warning(f"Failed to get tenant timing config: {e}")

        # Return defaults if config not available
        return {
            "wait_time_before_replying_ms": 60000,
            "typing_indicator_enabled": True,
            "min_typing_duration_ms": 1000,
            "max_typing_duration_ms": 5000,
            "message_reset_enabled": True,
            "natural_delays_enabled": True,
            "delay_variance_percent": 20,
        }

    async def _process_through_flow_processor(
        self, message_data: dict[str, Any], conversation_setup: Any, app_context: Any
    ):
        """Process through the flow processor with dependency injection."""
        # Build session ID for cancellation coordination
        session_id = self._build_session_id(
            message_data["sender_number"], conversation_setup.flow_id or "unknown"
        )

        logger.debug(
            f"Processing message for session {session_id}: {message_data.get('message_text', '')[:100]}"
        )

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
            channel_id=message_data[
                "receiver_number"
            ],  # WhatsApp business number for customer traceability
        )

        # Create dependencies with dependency injection
        session_manager = RedisSessionManager(app_context.store)
        thread_updater = WhatsAppThreadStatusUpdater()

        # Create clean flow processor with injected dependencies

        flow_processor = FlowProcessor(
            llm_client=app_context.llm,
            session_manager=session_manager,
            cancellation_manager=app_context.cancellation_manager,
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
                logger.info(
                    "Flow processing was cancelled for user %s (rapid messages)",
                    message_data["sender_number"],
                )
                # Don't send error message for cancellations - messages are being aggregated
                return PlainTextResponse("ok")

            # Check if this might be a duplicate/retry webhook to avoid sending multiple error messages
            if self._is_likely_retry(message_data, app_context):
                logger.warning(
                    "Likely webhook retry detected for user %s, not sending duplicate error message",
                    message_data["sender_number"],
                )
                return PlainTextResponse("ok")

            logger.error(
                "Flow processor error for user %s: %s",
                message_data["sender_number"],
                flow_response.error,
            )
            return self.adapter.build_sync_response(
                "Desculpe, erro interno do sistema. Tente novamente."
            )

        # Determine reply text
        if flow_response.result == FlowProcessingResult.ESCALATE:
            reply_text = flow_response.message or "Vou chamar alguém para ajudar você."
            logger.warning(
                "Flow escalated for tenant %s: %s", conversation_setup.tenant_id, reply_text
            )
        elif flow_response.result == FlowProcessingResult.TERMINAL:
            reply_text = flow_response.message or "Obrigado pela conversa!"
            logger.info(
                "Flow completed for tenant %s: %s", conversation_setup.tenant_id, reply_text
            )
        else:
            reply_text = flow_response.message or ""

        # Check for cancellation before naturalizing
        try:
            cancellation_manager = (
                flow_response.metadata.get("cancellation_manager")
                if flow_response.metadata
                else None
            )
            session_id = (
                flow_response.metadata.get("session_id") if flow_response.metadata else None
            )

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

        # Log details about flow modification responses
        if flow_response.metadata and flow_response.metadata.get("flow_modification_requested"):
            logger.info("=" * 60)
            logger.info("📱 WHATSAPP: FLOW MODIFICATION RESPONSE")
            logger.info("=" * 60)
            logger.info(
                f"Modification success: {flow_response.metadata.get('modification_success', False)}"
            )
            logger.info(
                f"Modification failed: {flow_response.metadata.get('modification_failed', False)}"
            )
            logger.info(
                f"Modification error: {flow_response.metadata.get('modification_error', 'None')}"
            )
            logger.info(f"Messages to send: {messages}")
            logger.info("=" * 60)

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
        # Messages are stored in metadata by flow processor
        if hasattr(flow_response, "metadata") and flow_response.metadata:
            metadata_messages = flow_response.metadata.get("messages")
            if metadata_messages and isinstance(metadata_messages, list):
                return metadata_messages

        # Fallback to message field
        if hasattr(flow_response, "message") and flow_response.message:
            return [{"text": flow_response.message, "delay_ms": 0}]

        # Final fallback
        return [{"text": "Entendi. Vou te ajudar com isso.", "delay_ms": 0}]

    async def _save_individual_messages(
        self,
        individual_messages: list[dict[str, Any]],
        conversation_setup: Any,
        message_data: dict[str, Any],
    ) -> None:
        """Save individual messages to database before aggregation.
        
        Args:
            individual_messages: List of individual message dicts from cancellation manager
            conversation_setup: Conversation setup with tenant/channel/thread info
            message_data: Original message data for provider_message_id
        """
        try:
            for msg in individual_messages:
                await message_logging_service.save_message_async(
                    tenant_id=conversation_setup.tenant_id,
                    channel_instance_id=conversation_setup.channel_instance_id,
                    thread_id=conversation_setup.thread_id,
                    contact_id=conversation_setup.contact_id,
                    text=msg["content"],
                    direction=MessageDirection.inbound,
                    provider_message_id=msg["id"],
                    payload={
                        "sequence": msg["sequence"],
                        "buffered_timestamp": msg["timestamp"],
                    },
                    status=MessageStatus.delivered,
                    delivered_at=datetime.fromtimestamp(msg["timestamp"], UTC),
                )
                logger.info(
                    f"Saved individual message #{msg['sequence']}: {msg['content'][:50]}..."
                )
        except Exception as exc:
            logger.warning("Failed to save individual messages: %s", exc)

    async def _log_whatsapp_messages(
        self, message_data: dict[str, Any], conversation_setup: Any, sync_reply: str
    ) -> None:
        """Log WhatsApp messages asynchronously."""
        try:
            # Skip inbound logging if already saved as individual messages
            if not message_data.get("skip_inbound_logging"):
                # Log inbound message (single message only)
                await message_logging_service.save_message_async(
                    tenant_id=conversation_setup.tenant_id,
                    channel_instance_id=conversation_setup.channel_instance_id,
                    thread_id=conversation_setup.thread_id,
                    contact_id=conversation_setup.contact_id,
                    text=message_data["message_text"],
                    direction=MessageDirection.inbound,
                    provider_message_id=(
                        message_data["params"].get("SmsMessageSid")
                        or message_data["params"].get("MessageSid")
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
            app_context.store.save(
                "system",
                key_suffix,
                {"reply_id": reply_id, "timestamp": int(datetime.now().timestamp())},
            )

            self.adapter.send_followups(
                message_data["sender_number"],
                message_data["receiver_number"],
                messages,
                reply_id,
                app_context.store,
                conversation_setup,  # Pass conversation context for database logging
            )
        except Exception as e:
            logger.warning("Failed to send WhatsApp follow-ups: %s", e)
