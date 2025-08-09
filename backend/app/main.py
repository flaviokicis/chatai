from typing import Optional, Dict, Any
import logging

from fastapi import FastAPI, Request, Header, HTTPException, status
from fastapi.responses import PlainTextResponse, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from .settings import get_settings
from .conversation import ConversationManager
import os
from langchain.chat_models import init_chat_model

app = FastAPI(title="Chatai Twilio Webhook", version="0.1.0")
logger = logging.getLogger("uvicorn.error")
conversation_manager = ConversationManager()


def build_validation_url(request: Request, public_base_url: Optional[str]) -> str:
    if public_base_url:
        base = public_base_url.rstrip("/")
        if request.url.query:
            return f"{base}{request.url.path}?{request.url.query}"
        return f"{base}{request.url.path}"
    return str(request.url)


@app.on_event("startup")
def _init_llm() -> None:
    settings = get_settings()
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key
    app.state.llm = init_chat_model(settings.llm_model, model_provider="google_genai")
    app.state.llm_model = settings.llm_model
    logger.info("LLM initialized: model=%s provider=%s", settings.llm_model, "google_genai")


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@app.post("/webhooks/twilio/whatsapp")
async def twilio_whatsapp_webhook(
    request: Request,
    x_twilio_signature: Optional[str] = Header(default=None, alias="X-Twilio-Signature"),
) -> Response:
    if not x_twilio_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Twilio-Signature header",
        )

    settings = get_settings()
    validator = RequestValidator(settings.twilio_auth_token)

    content_type = request.headers.get("content-type", "").lower()
    validation_url = build_validation_url(request, settings.public_base_url)
    logger.info(
        "Twilio webhook received: path=%s content_type=%s using_public_base_url=%s computed_url=%s",
        request.url.path,
        content_type,
        bool(settings.public_base_url),
        validation_url,
    )

    if content_type.startswith("application/json"):
        raw_body = await request.body()
        is_valid = validator.validate(validation_url, raw_body.decode("utf-8"), x_twilio_signature)
        if not is_valid:
            logger.warning(
                "Twilio signature validation failed (json). remote=%s signature_present=%s",
                request.client.host if request.client else "",
                bool(x_twilio_signature),
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")
        return PlainTextResponse("ok")

    form = await request.form()
    params: Dict[str, Any] = {k: str(v) for k, v in form.items()}

    is_valid = validator.validate(validation_url, params, x_twilio_signature)
    if not is_valid:
        logger.warning(
            "Twilio signature validation failed (form). remote=%s signature_present=%s",
            request.client.host if request.client else "",
            bool(x_twilio_signature),
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    from_number = params.get("From", "")
    body_text = params.get("Body", "")
    logger.info("Incoming WhatsApp message from %s: %s", from_number, body_text)

    # LLM-driven classification with tool calling; flow control remains deterministic.
    reply_text = conversation_manager.handle(from_number or "unknown", body_text, app.state.llm)

    twiml = MessagingResponse()
    twiml.message(reply_text)
    return Response(content=str(twiml), media_type="application/xml")
