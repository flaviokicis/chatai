from __future__ import annotations

from typing import Any, Protocol

from fastapi import Request, Response


class WhatsAppAdapter(Protocol):
    """Abstraction for WhatsApp channel providers.

    Implementations handle request validation/parsing, building the synchronous
    webhook response, and sending any follow-up messages with delays.
    """

    def validate_and_parse(self, request: Request, x_signature: str | None) -> dict[str, Any]:
        """Validate the inbound request and return parsed params.

        Must raise HTTPException on invalid signature.
        """

    def build_sync_response(self, text: str) -> Response:
        """Build the synchronous response body to return to the provider webhook."""

    def send_followups(
        self,
        to_number: str,
        from_number: str,
        plan: list[dict[str, object]] | None,
        reply_id: str | None = None,
        store: Any = None,
    ) -> None:
        """Send follow-up messages with delays, best-effort (may run in background).

        Implementations should skip the first item of the plan (it was already sent
        synchronously in the initial webhook response).
        
        Args:
            reply_id: Unique ID for this conversation turn, used for interruption handling
            store: Redis store for checking if reply is still current
        """

    def send_typing_indicator(self, to_phone: str, phone_number_id: str, message_id: str) -> None:
        """Send typing indicator to show that the bot is preparing a response.
        
        Args:
            to_phone: Phone number to send typing indicator to (clean format, no whatsapp: prefix)
            phone_number_id: WhatsApp Business phone number ID
            message_id: ID of the received message to mark as read
        """
