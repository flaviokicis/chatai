from __future__ import annotations

import requests
from langfuse import get_client

from app.settings import Settings


class SpeechToTextService:
    """Service for transcribing audio messages using OpenAI."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._langfuse = get_client()

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
        import logging

        logger = logging.getLogger(__name__)

        # Start Langfuse generation for cost tracking
        generation = self._langfuse.start_observation(
            name="audio_transcription",
            as_type="generation",
            model="whisper-1",  # OpenAI's Whisper model
            input=f"Audio file: {filename} ({len(audio_bytes)} bytes)",
            metadata={
                "operation": "audio_transcription",
                "file_size_bytes": len(audio_bytes),
                "language": "pt",
                "filename": filename,
            },
        )

        try:
            headers = {"Authorization": f"Bearer {self._settings.openai_api_key}"}
            files = {"file": (filename, audio_bytes)}
            data = {
                "model": "whisper-1",  # Using standard Whisper model name
                "language": "pt",  # Portuguese language hint for better accuracy
            }

            logger.info(
                "Starting audio transcription with OpenAI (size: %d bytes)", len(audio_bytes)
            )

            resp = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
                timeout=300,
            )
            resp.raise_for_status()

            response_data = resp.json()
            transcribed_text = response_data.get("text", "")

            # Calculate audio duration in seconds (approximate based on file size)
            # WhatsApp audio is typically Opus at ~16kbps = 2KB/s
            estimated_duration_seconds = len(audio_bytes) / 2000

            # Update Langfuse with output and estimated usage
            generation.update(
                output=transcribed_text,
                usage={
                    "input": estimated_duration_seconds,  # Audio duration in seconds
                    "output": len(transcribed_text.split()),  # Word count
                    "unit": "SECONDS",  # Whisper is billed per second of audio
                },
                metadata={
                    "transcribed_length": len(transcribed_text),
                    "estimated_duration_seconds": estimated_duration_seconds,
                    "language_detected": response_data.get("language", "pt"),
                },
            )
            generation.end()

            logger.info("Audio transcription completed: %r", transcribed_text)

            return transcribed_text

        except Exception as e:
            # Track error in Langfuse
            generation.update(
                output=f"ERROR: {e}", metadata={"error": str(e), "error_type": type(e).__name__}
            )
            generation.end()
            raise
