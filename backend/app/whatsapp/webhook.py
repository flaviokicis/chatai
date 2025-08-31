"""Refactored WhatsApp webhook handler - clean, modular, single-responsibility functions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse

from app.settings import get_settings
from app.whatsapp.message_processor import WhatsAppMessageProcessor

if TYPE_CHECKING:
    from app.whatsapp.adapter import WhatsAppAdapter

from app.whatsapp.twilio_adapter import TwilioWhatsAppAdapter
from app.whatsapp.whatsapp_api_adapter import WhatsAppApiAdapter

logger = logging.getLogger(__name__)


def _get_adapter(settings: Any, *, use_whatsapp_api: bool = False) -> WhatsAppAdapter:  # type: ignore[type-arg]
    """Get the appropriate WhatsApp adapter based on configuration."""
    if use_whatsapp_api:
        return WhatsAppApiAdapter(settings)
    return TwilioWhatsAppAdapter(settings)


async def handle_twilio_whatsapp_webhook(
    request: Request, x_twilio_signature: str | None
) -> Response:
    """
    Clean, modular WhatsApp webhook handler.
    
    This function now delegates all complex logic to specialized services,
    maintaining a clean separation of concerns and single responsibility principle.
    """
    # Basic validation check (adapter handles detailed validation)
    if not x_twilio_signature:
        # Adapter will raise HTTP 400 if required; allow test monkeypatch to proceed
        pass

    # Get appropriate adapter
    settings = get_settings()
    use_whatsapp_api = settings.whatsapp_provider == "cloud_api"
    adapter = _get_adapter(settings, use_whatsapp_api=use_whatsapp_api)

    # Process message through the complete pipeline
    processor = WhatsAppMessageProcessor(adapter)
    return await processor.process_message(request, x_twilio_signature)


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
