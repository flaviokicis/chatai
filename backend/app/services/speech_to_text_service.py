from __future__ import annotations

import requests

from app.settings import Settings


class SpeechToTextService:
    """Service for transcribing audio messages using OpenAI."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def transcribe_twilio_media(self, media_url: str) -> str:
        """Download Twilio media and transcribe to text."""
        auth = None
        account_sid = getattr(self._settings, "twilio_account_sid", None)
        auth_token = getattr(self._settings, "twilio_auth_token", None)
        if account_sid and auth_token:
            auth = (account_sid, auth_token)
        response = requests.get(media_url, auth=auth, timeout=30)
        response.raise_for_status()
        return self._transcribe(response.content, "audio.ogg")

    def transcribe_whatsapp_api_media(self, media_id: str) -> str:
        """Fetch WhatsApp Cloud API media and transcribe to text."""
        access_token = self._settings.whatsapp_access_token
        meta_resp = requests.get(
            f"https://graph.facebook.com/v22.0/{media_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        meta_resp.raise_for_status()
        media_url = meta_resp.json().get("url")
        media_resp = requests.get(
            media_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        media_resp.raise_for_status()
        return self._transcribe(media_resp.content, "audio.ogg")

    def _transcribe(self, audio_bytes: bytes, filename: str) -> str:
        headers = {"Authorization": f"Bearer {self._settings.openai_api_key}"}
        files = {"file": (filename, audio_bytes)}
        data = {"model": "gpt-4o-mini-transcribe"}
        resp = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json().get("text", "")
