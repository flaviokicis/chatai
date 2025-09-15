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

from app.whatsapp.whatsapp_api_adapter import WhatsAppApiAdapter

logger = logging.getLogger(__name__)


def _get_adapter(settings: Any, *, use_whatsapp_api: bool = False) -> WhatsAppAdapter:  # type: ignore[type-arg]
    """Get the WhatsApp Cloud API adapter."""
    return WhatsAppApiAdapter(settings)


async def handle_twilio_whatsapp_webhook(
    request: Request, x_twilio_signature: str | None
) -> Response:
    """
    Clean, modular WhatsApp webhook handler.

    This function now delegates all complex logic to specialized services,
    maintaining a clean separation of concerns and single responsibility principle.
    """
    try:
        # Get appropriate adapter
        settings = get_settings()
        use_whatsapp_api = settings.whatsapp_provider == "cloud_api"
        adapter = _get_adapter(settings, use_whatsapp_api=use_whatsapp_api)

        # Process message through the complete pipeline
        processor = WhatsAppMessageProcessor(adapter)
        return await processor.process_message(request, x_twilio_signature)

    except HTTPException as e:
        # Log webhook validation failures but return "ok" to prevent retries
        client_ip = request.headers.get(
            "x-forwarded-for", request.client.host if request.client else "unknown"
        )
        if e.status_code == 400:
            logger.warning("WhatsApp webhook missing signature from IP %s", client_ip)
        elif e.status_code == 403:
            logger.warning("WhatsApp webhook invalid signature from IP %s", client_ip)
        else:
            logger.warning(
                "WhatsApp webhook validation error %d from IP %s: %s",
                e.status_code,
                client_ip,
                e.detail,
            )

        # Return "ok" to prevent webhook retries while logging the issue
        return PlainTextResponse("ok")

    except Exception as e:
        # Log unexpected errors but still return "ok" to prevent webhook retries
        client_ip = request.headers.get(
            "x-forwarded-for", request.client.host if request.client else "unknown"
        )
        logger.error("Unexpected error processing WhatsApp webhook from IP %s: %s", client_ip, e)
        return PlainTextResponse("ok")


async def handle_whatsapp_webhook_verification(
    request: Request, hub_mode: str, hub_challenge: str, hub_verify_token: str
) -> Response:
    """Handle WhatsApp webhook verification for Cloud API."""
    settings = get_settings()

    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("WhatsApp webhook verified successfully")
        return PlainTextResponse(hub_challenge, status_code=200)
    logger.warning(
        "WhatsApp webhook verification failed: mode=%s, token_valid=%s",
        hub_mode,
        hub_verify_token == settings.whatsapp_verify_token,
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed")
