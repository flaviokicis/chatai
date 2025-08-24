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
