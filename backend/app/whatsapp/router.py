from __future__ import annotations

from fastapi import APIRouter, Header, Request, Response

from .webhook import handle_twilio_whatsapp_webhook

router = APIRouter()


@router.post("/webhooks/twilio/whatsapp")
async def twilio_whatsapp_webhook_route(
    request: Request,
    x_twilio_signature: str | None = Header(default=None, alias="X-Twilio-Signature"),
) -> Response:
    return await handle_twilio_whatsapp_webhook(request, x_twilio_signature)
