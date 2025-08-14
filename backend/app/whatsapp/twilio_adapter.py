from __future__ import annotations

import logging
import threading
import time
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from twilio.rest import Client as TwilioClient
from twilio.twiml.messaging_response import MessagingResponse


class _Settings(Any):  # loose protocol for settings access
    twilio_auth_token: str
    twilio_account_sid: str | None
    public_base_url: str | None


class TwilioWhatsAppAdapter:
    def __init__(self, settings: _Settings) -> None:  # type: ignore[valid-type]
        self._settings = settings
        # Delegate validation/parsing to legacy handler to preserve test monkeypatches
        from .twilio import TwilioWhatsAppHandler

        self._handler = TwilioWhatsAppHandler(settings)
        self._logger = logging.getLogger("uvicorn.error")

    async def validate_and_parse(self, request: Request, x_signature: str | None) -> dict[str, Any]:
        # Monkeypatch-friendly: tests patch TwilioWhatsAppHandler.validate_and_parse
        return await self._handler.validate_and_parse(request, x_signature)

    def build_sync_response(self, text: str) -> Response:
        twiml = MessagingResponse()
        twiml.message(text)
        return Response(content=str(twiml), media_type="application/xml")

    def send_followups(
        self, to_number: str, from_number: str, plan: list[dict[str, object]] | None
    ) -> None:
        if not plan or len(plan) <= 1:
            return
        account_sid = getattr(self._settings, "twilio_account_sid", None)
        auth_token = getattr(self._settings, "twilio_auth_token", None)
        if not account_sid or not auth_token:
            return
        client = TwilioClient(account_sid, auth_token)
        try:
            total = max(0, len(plan) - 1)
            preview = [
                f"{int(m.get('delay_ms', 0))}ms: {str(m.get('text', '')).strip()}"
                for m in plan[1:]
                if isinstance(m, dict)
            ]
            self._logger.info(
                "Dispatching %d WhatsApp follow-ups to %s: %s", total, to_number, preview
            )
        except Exception:
            pass

        def _run() -> None:
            for i, msg in enumerate(plan[1:], start=1):
                try:
                    delay_ms = int(msg.get("delay_ms", 800)) if isinstance(msg, dict) else 800
                    text = str(msg.get("text", "")) if isinstance(msg, dict) else ""
                    if not text:
                        continue
                    try:
                        self._logger.info(
                            "Sending WhatsApp follow-up #%d after %dms: %r", i, delay_ms, text
                        )
                    except Exception:
                        pass
                    time.sleep(max(0, delay_ms) / 1000.0)
                    client.messages.create(to=to_number, from_=from_number, body=text)
                except Exception:
                    try:
                        self._logger.warning(
                            "Failed to send WhatsApp follow-up #%d to %s", i, to_number
                        )
                    except Exception:
                        pass
                    continue

        threading.Thread(target=_run, daemon=True).start()
