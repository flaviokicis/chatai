"""Audio validation service for WhatsApp media messages."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


class AudioValidationService:
    """Service for validating audio messages before processing."""

    def __init__(self, max_duration_seconds: int = 300) -> None:  # 5 minutes default
        self.max_duration_seconds = max_duration_seconds

    def validate_audio_duration(self, audio_bytes: bytes) -> tuple[bool, float | None, str | None]:
        """
        Validate audio duration from audio bytes using audioread.

        Returns:
            tuple: (is_valid, duration_seconds, error_message)
        """
        try:
            duration = self._get_audio_duration_audioread(audio_bytes)

            if duration is None:
                # If we can't determine duration, reject to be safe (prevent large audio costs)
                logger.warning("Could not determine audio duration, rejecting for safety")
                return False, None, "Could not determine audio duration"

            is_valid = duration <= self.max_duration_seconds
            error_msg = None
            if not is_valid:
                error_msg = f"Audio duration ({duration:.1f}s) exceeds maximum allowed ({self.max_duration_seconds}s)"

            return is_valid, duration, error_msg

        except Exception as e:
            logger.warning("Failed to validate audio duration: %s", e)
            # On error, reject to be safe (prevent unexpected costs)
            return False, None, f"Audio validation error: {e}"

    def _get_audio_duration_audioread(self, audio_bytes: bytes) -> float | None:
        """Get audio duration using audioread library."""
        try:
            import tempfile
            from pathlib import Path

            import audioread

            # Write bytes to temporary file (audioread needs a file path)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name

            try:
                # Use audioread to get duration
                with audioread.audio_open(temp_path) as audio_file:
                    return float(audio_file.duration)
            finally:
                # Clean up temp file
                try:
                    Path(temp_path).unlink()
                except Exception:
                    pass

        except ImportError:
            logger.warning("audioread not available - audio duration validation disabled")
        except Exception as e:
            logger.debug("audioread failed to parse audio: %s", e)

        return None

    def validate_twilio_media_duration(self, media_url: str, auth: tuple[str, str] | None = None) -> tuple[bool, float | None, str | None]:
        """
        Validate audio duration for Twilio media URL.

        Args:
            media_url: Twilio media URL
            auth: Twilio auth tuple (account_sid, auth_token)

        Returns:
            tuple: (is_valid, duration_seconds, error_message)
        """
        try:
            response = requests.get(media_url, auth=auth, timeout=30)
            response.raise_for_status()
            return self.validate_audio_duration(response.content)
        except Exception as e:
            logger.warning("Failed to download Twilio media for validation: %s", e)
            # On error, reject to be safe (prevent unexpected costs)
            return False, None, f"Failed to download audio: {e}"

    def validate_whatsapp_api_media_duration(self, media_id: str, access_token: str) -> tuple[bool, float | None, str | None]:
        """
        Validate audio duration for WhatsApp Cloud API media.

        Args:
            media_id: WhatsApp media ID
            access_token: WhatsApp access token

        Returns:
            tuple: (is_valid, duration_seconds, error_message)
        """
        try:
            # Get media URL from WhatsApp API
            meta_resp = requests.get(
                f"https://graph.facebook.com/v22.0/{media_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            meta_resp.raise_for_status()
            media_url = meta_resp.json().get("url")

            if not media_url:
                # On error, allow the audio through to avoid blocking legitimate messages
                return True, None, "No media URL in WhatsApp API response"

            # Download media content
            media_resp = requests.get(
                media_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            media_resp.raise_for_status()

            return self.validate_audio_duration(media_resp.content)

        except Exception as e:
            logger.warning("Failed to download WhatsApp API media for validation: %s", e)
            # On error, reject to be safe (prevent unexpected costs)
            return False, None, f"Failed to download audio: {e}"
