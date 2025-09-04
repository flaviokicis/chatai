from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Protocol

import requests
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse


class WhatsAppApiSettings(Protocol):
    """Protocol for settings needed by WhatsApp API adapter."""

    whatsapp_verify_token: str
    whatsapp_access_token: str


logger = logging.getLogger(__name__)


class WhatsAppApiAdapter:
    """WhatsApp API adapter for direct WhatsApp Business API integration."""

    def __init__(self, settings: WhatsAppApiSettings) -> None:
        self._settings = settings
        self._last_sender = ""
        self._last_receiver = ""

    async def validate_and_parse(
        self, request: Request, x_signature: str | None
    ) -> dict[str, Any]:
        """Validate and parse WhatsApp Cloud API webhook requests."""

        # For webhook verification (GET requests), we handle this in the router/webhook handler
        # This method is primarily for POST requests with actual messages

        try:
            body = await request.body()
            if not body:
                return {}

            data = json.loads(body.decode("utf-8"))

            # WhatsApp Cloud API sends webhook data in a specific structure
            # Extract the message data from the webhook payload
            parsed_data = self._extract_message_data(data)
            return parsed_data

        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
            )
        except Exception as e:
            logger.error("Error parsing WhatsApp Cloud API webhook: %s", str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to parse webhook payload",
            )

    def _extract_message_data(self, webhook_data: dict[str, Any]) -> dict[str, Any]:
        """Extract message data from WhatsApp Cloud API webhook payload."""

        try:
            # WhatsApp Cloud API structure:
            # {
            #   "object": "whatsapp_business_account",
            #   "entry": [
            #     {
            #       "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            #       "changes": [
            #         {
            #           "field": "messages",
            #           "value": {
            #             "messaging_product": "whatsapp",
            #             "metadata": { ... },
            #             "messages": [ ... ]
            #           }
            #         }
            #       ]
            #     }
            #   ]
            # }

            if not webhook_data.get("entry"):
                return {}

            entry = webhook_data["entry"][0]
            if not entry.get("changes"):
                return {}

            change = entry["changes"][0]
            if change.get("field") != "messages":
                return {}

            value = change.get("value", {})
            messages = value.get("messages", [])

            if not messages:
                return {}

            # Extract the first message
            message = messages[0]

            # Convert to format expected by the rest of the system
            # (similar to Twilio format for compatibility)
            from_number = f"whatsapp:{message.get('from', '')}"
            to_number = f"whatsapp:{value.get('metadata', {}).get('phone_number_id', '')}"

            # Store for use in build_sync_response
            self._last_sender = from_number
            self._last_receiver = to_number

            return {
                "From": from_number,
                "To": to_number,
                "Body": self._extract_message_text(message),
                "MessageSid": message.get("id", ""),
                "MessageType": message.get("type", "text"),
                "WhatsAppRawMessage": message,  # Keep raw message for advanced processing
            }

        except (KeyError, IndexError, TypeError) as e:
            logger.warning("Failed to extract message data from webhook: %s", str(e))
            return {}

    def _extract_message_text(self, message: dict[str, Any]) -> str:
        """Extract text content from WhatsApp message object."""

        message_type = message.get("type", "text")

        if message_type == "text":
            return message.get("text", {}).get("body", "")
        if message_type == "button":
            return message.get("button", {}).get("text", "")
        if message_type == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                return interactive.get("button_reply", {}).get("title", "")
            if interactive.get("type") == "list_reply":
                return interactive.get("list_reply", {}).get("title", "")

        # For other message types (image, document, etc.), return a placeholder
        return f"[{message_type} message]"

    def build_sync_response(self, text: str) -> Response:
        """Build synchronous response for WhatsApp Cloud API."""

        # For WhatsApp Cloud API, we need to actively send the first message via API
        if text and self._last_sender:
            try:
                # Extract clean phone number from WhatsApp format (whatsapp:+1234567890)
                clean_to = self._last_sender.replace("whatsapp:", "")
                # Extract phone_number_id from receiver (our WhatsApp Business number)
                phone_number_id = self._last_receiver.replace("whatsapp:", "")
                self._send_message_via_api(clean_to, text, phone_number_id)
                logger.debug("Successfully sent sync WhatsApp message to %s", clean_to)
            except Exception as e:
                logger.error("Failed to send sync WhatsApp message: %s", e)

        # WhatsApp Cloud API expects a simple 200 OK response for webhook acknowledgment
        return PlainTextResponse("ok", status_code=200)

    def send_followups(
        self,
        to_number: str,
        from_number: str,
        plan: list[dict[str, object]] | None,
        reply_id: str | None = None,
        store: object = None,
    ) -> None:
        """Send follow-up messages using WhatsApp Cloud API."""

        if not plan or len(plan) <= 1:
            return

        # Extract phone number from WhatsApp format (whatsapp:+1234567890)
        clean_to = to_number.replace("whatsapp:", "")

        def _run() -> None:
            for i, msg in enumerate(
                plan[1:], start=1
            ):  # Skip first message (already sent)
                try:
                    delay_ms = (
                        int(msg.get("delay_ms", 800)) if isinstance(msg, dict) else 800
                    )
                    text = str(msg.get("text", "")) if isinstance(msg, dict) else ""
                    if not text:
                        continue

                    logger.info(
                        "Sending WhatsApp follow-up #%d after %dms: %r",
                        i,
                        delay_ms,
                        text,
                    )

                    time.sleep(max(0, delay_ms) / 1000.0)

                    # Check if this reply is still current (user hasn't sent a new message)
                    if reply_id and store:
                        try:
                            from app.core.redis_keys import redis_keys
                            current_reply_key = redis_keys.current_reply_key(to_number)
                            key_suffix = current_reply_key.replace("chatai:state:system:", "")
                            current_data = store.load("system", key_suffix)
                            if current_data and isinstance(current_data, dict):
                                current_reply_id = current_data.get("reply_id")
                                if current_reply_id != reply_id:
                                    logger.info(
                                        "Cancelling WhatsApp follow-up #%d to %s (user sent new message, reply_id changed %s -> %s)",
                                        i, to_number, reply_id, current_reply_id
                                    )
                                    return  # Stop sending remaining follow-ups
                        except Exception as e:
                            logger.warning("Failed to check reply interrupt status: %s", e)
                            # Continue sending on error - don't break the flow

                    # Use the phone_number_id from the original message
                    phone_number_id = from_number.replace("whatsapp:", "")
                    self._send_message_via_api(clean_to, text, phone_number_id)

                except Exception as e:
                    logger.warning(
                        "Failed to send WhatsApp follow-up #%d to %s: %s",
                        i,
                        to_number,
                        str(e),
                    )
                    continue

        threading.Thread(target=_run, daemon=True).start()

    def send_typing_indicator(self, to_phone: str, phone_number_id: str, message_id: str) -> None:
        """Send typing indicator using WhatsApp Cloud API."""

        try:
            # WhatsApp Cloud API endpoint for typing indicators
            url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"

            headers = {
                "Authorization": f"Bearer {self._settings.whatsapp_access_token}",
                "Content-Type": "application/json",
            }

            payload = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
                "typing_indicator": {
                    "type": "text"
                }
            }

            logger.debug("Sending WhatsApp typing indicator to %s for message %s", to_phone, message_id)
            response = requests.post(url, headers=headers, json=payload, timeout=10)

            if response.status_code == 200:
                logger.debug("Successfully sent WhatsApp typing indicator to %s", to_phone)
            else:
                logger.warning(
                    "Failed to send WhatsApp typing indicator: %d %s - Response: %s",
                    response.status_code,
                    response.text,
                    response.headers,
                )

        except Exception as e:
            logger.warning("Error sending WhatsApp typing indicator: %s", str(e))

    def _send_message_via_api(self, to_phone: str, text: str, phone_number_id: str) -> None:
        """Send message using WhatsApp Cloud API."""

        try:
            # Fix Brazilian mobile number format
            # WhatsApp webhooks may send old 8-digit format (e.g., 553188245287)
            # but the API expects new 9-digit format (e.g., 5531988245287)
            # 
            # Background: Brazil added a 9th digit to mobile numbers starting in 2012-2016.
            # WhatsApp's webhook sometimes sends the old format without the 9, but the API
            # requires the new format. This is a known issue in the WhatsApp developer community.
            # See: https://github.com/pedroslopez/whatsapp-web.js/issues/1967
            
            original_phone = to_phone  # Keep original for fallback
            converted_phone = None
            
            if to_phone.startswith("55") and len(to_phone) == 12:  # Brazilian number with 8 digits
                # Check if it's a valid Brazilian area code (11-99)
                area_code = to_phone[2:4]
                if area_code.isdigit() and 11 <= int(area_code) <= 99:
                    # Since we can't reliably determine mobile vs landline from the number alone,
                    # we'll try adding the 9 prefix and fall back to original if it fails
                    converted_phone = to_phone[:4] + "9" + to_phone[4:]
                    logger.debug("Will try Brazilian number with 9-digit format: %s -> %s", 
                               original_phone, converted_phone)
                    to_phone = converted_phone

            # WhatsApp Cloud API endpoint - use the Phone Number ID from our database
            url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"

            headers = {
                "Authorization": f"Bearer {self._settings.whatsapp_access_token}",
                "Content-Type": "application/json",
            }

            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "text": {"body": text},
            }

            logger.debug("Sending WhatsApp message to %s via %s", to_phone, url)
            response = requests.post(url, headers=headers, json=payload, timeout=10)

            if response.status_code == 200:
                logger.debug("Successfully sent WhatsApp message to %s", to_phone)
            elif response.status_code == 400 and converted_phone and "131030" in response.text:
                # If we get the "recipient not in allowed list" error and we tried a conversion,
                # fall back to the original number format
                logger.warning("9-digit format failed, trying original 8-digit format: %s", original_phone)
                payload["to"] = original_phone
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                
                if response.status_code == 200:
                    logger.info("Successfully sent with original format: %s", original_phone)
                else:
                    logger.error(
                        "Failed to send WhatsApp message with both formats: %d %s",
                        response.status_code,
                        response.text,
                    )
            else:
                logger.error(
                    "Failed to send WhatsApp message: %d %s - Response: %s",
                    response.status_code,
                    response.text,
                    response.headers,
                )

        except Exception as e:
            logger.error("Error sending WhatsApp message via API: %s", str(e))

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str | None:
        """Verify webhook challenge for WhatsApp Cloud API."""

        if mode == "subscribe" and token == self._settings.whatsapp_verify_token:
            logger.info("WhatsApp webhook verified successfully")
            return challenge
        logger.warning(
            "WhatsApp webhook verification failed: mode=%s, token_valid=%s",
            mode,
            token == self._settings.whatsapp_verify_token,
        )
        return None
