from __future__ import annotations

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import PlainTextResponse

from .webhook import handle_twilio_whatsapp_webhook, handle_whatsapp_webhook_verification

router = APIRouter()


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook_post(
    request: Request,
    x_twilio_signature: str | None = Header(default=None, alias="X-Twilio-Signature"),
) -> Response:
    """Handle incoming WhatsApp messages (POST) - supports both Twilio and Cloud API."""
    return await handle_twilio_whatsapp_webhook(request, x_twilio_signature)


# Legacy route for backwards compatibility
@router.post("/webhooks/twilio/whatsapp")
async def twilio_whatsapp_webhook_legacy(
    request: Request,
    x_twilio_signature: str | None = Header(default=None, alias="X-Twilio-Signature"),
) -> Response:
    """Legacy Twilio WhatsApp webhook (redirects to new unified endpoint)."""
    return await handle_twilio_whatsapp_webhook(request, x_twilio_signature)


@router.get("/webhooks/whatsapp")
async def whatsapp_webhook_get(
    request: Request,
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"), 
    hub_verify_token: str = Query(alias="hub.verify_token"),
) -> Response:
    """Handle WhatsApp webhook verification (GET)."""
    return await handle_whatsapp_webhook_verification(
        request, hub_mode, hub_challenge, hub_verify_token
    )
