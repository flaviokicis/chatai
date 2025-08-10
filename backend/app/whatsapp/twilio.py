from __future__ import annotations

from typing import Any, Protocol

from fastapi import HTTPException, Request, status
from twilio.request_validator import RequestValidator


class SignatureProvider(Protocol):
    twilio_auth_token: str
    public_base_url: str | None


class TwilioWhatsAppHandler:
    def __init__(self, settings: SignatureProvider) -> None:
        self._settings = settings
        self._validator = RequestValidator(settings.twilio_auth_token)

    def _build_validation_url(self, request: Request) -> str:
        public_base_url = self._settings.public_base_url
        if public_base_url:
            base = public_base_url.rstrip("/")
            if request.url.query:
                return f"{base}{request.url.path}?{request.url.query}"
            return f"{base}{request.url.path}"
        return str(request.url)

    async def validate_and_parse(
        self, request: Request, x_twilio_signature: str | None
    ) -> dict[str, Any]:
        if not x_twilio_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing X-Twilio-Signature header",
            )

        content_type = request.headers.get("content-type", "").lower()
        validation_url = self._build_validation_url(request)

        if content_type.startswith("application/json"):
            raw_body = await request.body()
            is_valid = self._validator.validate(
                validation_url, raw_body.decode("utf-8"), x_twilio_signature
            )
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature"
                )
            return {}

        form = await request.form()
        params: dict[str, Any] = {k: str(v) for k, v in form.items()}
        is_valid = self._validator.validate(validation_url, params, x_twilio_signature)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")
        return params
