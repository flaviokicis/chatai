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
        Validate audio duration from audio bytes using mutagen.

        Returns:
            tuple: (is_valid, duration_seconds, error_message)
        """
        try:
            logger.debug(
                "Starting audio duration validation, max allowed: %ds", self.max_duration_seconds
            )

            duration = self._get_audio_duration_audioread(audio_bytes)

            if duration is None:
                # If we can't determine duration, reject to be safe (prevent large audio costs)
                logger.warning(
                    "Could not determine audio duration, rejecting for safety (bytes received: %d)",
                    len(audio_bytes) if audio_bytes else 0,
                )
                return False, None, "Could not determine audio duration"

            logger.debug(
                "Audio duration determined: %.2fs (max allowed: %ds)",
                duration,
                self.max_duration_seconds,
            )

            is_valid = duration <= self.max_duration_seconds
            error_msg = None
            if not is_valid:
                error_msg = f"Audio duration ({duration:.1f}s) exceeds maximum allowed ({self.max_duration_seconds}s)"
                logger.warning("Audio rejected - too long: %s", error_msg)
            else:
                logger.debug("Audio duration OK: %.2fs <= %ds", duration, self.max_duration_seconds)

            return is_valid, duration, error_msg

        except Exception as e:
            logger.error("Failed to validate audio duration: %s", e, exc_info=True)
            # On error, reject to be safe (prevent unexpected costs)
            return False, None, f"Audio validation error: {e}"

    def _get_audio_duration_audioread(self, audio_bytes: bytes) -> float | None:
        """Get audio duration using mutagen library (pure Python, no ffmpeg needed)."""
        try:
            import tempfile
            from pathlib import Path

            # Log audio bytes info
            logger.debug("Audio validation: Processing %d bytes of audio data", len(audio_bytes))

            # Check if we have any data
            if not audio_bytes:
                logger.warning("Audio validation failed: Empty audio data received")
                return None

            # Check file signature to identify format
            file_signature = audio_bytes[:4] if len(audio_bytes) >= 4 else b""
            logger.debug("Audio file signature: %s", file_signature.hex())

            # OGG files start with 'OggS'
            if file_signature == b"OggS":
                logger.debug("Detected OGG container format")
            else:
                logger.warning(
                    "Unknown audio format (signature: %s), expected OGG", file_signature.hex()
                )

            # Try to import mutagen for OGG/Opus files
            try:
                from mutagen.oggopus import OggOpus
                from mutagen.oggvorbis import OggVorbis

                logger.debug("Mutagen libraries imported successfully")
            except ImportError as e:
                logger.error("Failed to import mutagen: %s", e)
                return None

            # Write bytes to temporary file (mutagen needs a file path)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name
                logger.debug("Wrote audio to temp file: %s (%d bytes)", temp_path, len(audio_bytes))

            try:
                # Try OggOpus first (WhatsApp commonly uses Opus codec)
                try:
                    logger.debug("Attempting to parse as OggOpus...")
                    audio = OggOpus(temp_path)
                    if audio.info and hasattr(audio.info, "length"):
                        duration = float(audio.info.length)
                        logger.info(
                            "Successfully parsed OggOpus: duration=%.2fs, bitrate=%s, channels=%s",
                            duration,
                            getattr(audio.info, "bitrate", "unknown"),
                            getattr(audio.info, "channels", "unknown"),
                        )
                        return duration
                    logger.warning("OggOpus parsed but no duration info available")
                except Exception as e:
                    logger.debug("Not an Opus file or parsing failed: %s", str(e))

                # Fall back to OggVorbis
                try:
                    logger.debug("Attempting to parse as OggVorbis...")
                    audio = OggVorbis(temp_path)
                    if audio.info and hasattr(audio.info, "length"):
                        duration = float(audio.info.length)
                        logger.info(
                            "Successfully parsed OggVorbis: duration=%.2fs, bitrate=%s, channels=%s",
                            duration,
                            getattr(audio.info, "bitrate", "unknown"),
                            getattr(audio.info, "channels", "unknown"),
                        )
                        return duration
                    logger.warning("OggVorbis parsed but no duration info available")
                except Exception as e:
                    logger.debug("Not a Vorbis file or parsing failed: %s", str(e))

                logger.error(
                    "Could not parse OGG file with mutagen - file might be corrupted, incomplete, or use unsupported codec"
                )

                # Try to read more details about why it failed
                try:
                    # Check file size
                    from pathlib import Path

                    file_size = Path(temp_path).stat().st_size
                    logger.debug("Temp file size on disk: %d bytes", file_size)

                    # Read first 100 bytes for debugging
                    with open(temp_path, "rb") as f:
                        header = f.read(100)
                        logger.debug("File header (first 100 bytes): %s", header[:100].hex())
                except Exception as debug_error:
                    logger.debug("Error reading file details: %s", debug_error)

                return None

            finally:
                # Clean up temp file
                try:
                    Path(temp_path).unlink()
                    logger.debug("Cleaned up temp file: %s", temp_path)
                except Exception as e:
                    logger.debug("Failed to clean up temp file %s: %s", temp_path, e)

        except ImportError as e:
            logger.error("mutagen not available - audio duration validation disabled: %s", e)
        except Exception as e:
            logger.error("Unexpected error in audio validation: %s", e, exc_info=True)

        return None

    def validate_twilio_media_duration(
        self, media_url: str, auth: tuple[str, str] | None = None
    ) -> tuple[bool, float | None, str | None]:
        """
        Validate audio duration for Twilio media URL.

        Args:
            media_url: Twilio media URL
            auth: Twilio auth tuple (account_sid, auth_token)

        Returns:
            tuple: (is_valid, duration_seconds, error_message)
        """
        try:
            logger.debug(
                "Starting Twilio media validation for URL: %s",
                media_url[:100] + "..." if len(media_url) > 100 else media_url,
            )
            logger.debug("Using auth: %s", "Yes" if auth else "No")

            response = requests.get(media_url, auth=auth, timeout=30)

            logger.debug(
                "Twilio media response: status=%d, content_size=%d bytes, content_type=%s",
                response.status_code,
                len(response.content),
                response.headers.get("content-type", "unknown"),
            )

            if response.status_code != 200:
                logger.error(
                    "Twilio media download failed: status=%d, headers=%s",
                    response.status_code,
                    dict(response.headers),
                )
                return False, None, f"Twilio download error: {response.status_code}"

            response.raise_for_status()

            logger.debug(
                "Downloaded %d bytes of Twilio audio data, validating...", len(response.content)
            )
            is_valid, duration, error_msg = self.validate_audio_duration(response.content)

            if is_valid:
                logger.info("Twilio audio validation successful: duration=%.2fs", duration or 0)
            else:
                logger.warning(
                    "Twilio audio validation failed: error=%s, duration=%s", error_msg, duration
                )

            return is_valid, duration, error_msg

        except requests.exceptions.Timeout:
            logger.error("Timeout downloading Twilio media: %s", media_url[:100])
            return False, None, "Timeout downloading audio"
        except requests.exceptions.RequestException as e:
            logger.error(
                "Network error downloading Twilio media: %s, error=%s",
                media_url[:100],
                e,
                exc_info=True,
            )
            return False, None, f"Network error: {e}"
        except Exception as e:
            logger.error(
                "Unexpected error in Twilio media validation: %s, error=%s",
                media_url[:100],
                e,
                exc_info=True,
            )
            # On error, reject to be safe (prevent unexpected costs)
            return False, None, f"Failed to download audio: {e}"

    def validate_whatsapp_api_media_duration(
        self, media_id: str, access_token: str
    ) -> tuple[bool, float | None, str | None]:
        """
        Validate audio duration for WhatsApp Cloud API media.

        Args:
            media_id: WhatsApp media ID
            access_token: WhatsApp access token

        Returns:
            tuple: (is_valid, duration_seconds, error_message)
        """
        try:
            logger.debug("Starting WhatsApp API media validation for media_id: %s", media_id)

            # Get media URL from WhatsApp API
            api_url = f"https://graph.facebook.com/v22.0/{media_id}"
            logger.debug("Fetching media metadata from: %s", api_url)

            meta_resp = requests.get(
                api_url,
                headers={
                    "Authorization": f"Bearer {access_token[:10]}..."
                },  # Log partial token for security
                timeout=30,
            )

            logger.debug(
                "WhatsApp API metadata response: status=%d, size=%d bytes",
                meta_resp.status_code,
                len(meta_resp.content),
            )

            if meta_resp.status_code != 200:
                logger.error(
                    "WhatsApp API error: status=%d, response=%s",
                    meta_resp.status_code,
                    meta_resp.text[:500],
                )
                return False, None, f"WhatsApp API error: {meta_resp.status_code}"

            meta_resp.raise_for_status()

            meta_data = meta_resp.json()
            logger.debug(
                "WhatsApp media metadata: %s", {k: v for k, v in meta_data.items() if k != "url"}
            )  # Don't log full URL

            media_url = meta_data.get("url")
            mime_type = meta_data.get("mime_type", "unknown")
            file_size = meta_data.get("file_size", 0)

            logger.debug("Media details: mime_type=%s, file_size=%s bytes", mime_type, file_size)

            if not media_url:
                logger.error("No media URL in WhatsApp API response. Full response: %s", meta_data)
                # On error, allow the audio through to avoid blocking legitimate messages
                return True, None, "No media URL in WhatsApp API response"

            # Download media content
            logger.debug("Downloading media content from WhatsApp CDN...")
            media_resp = requests.get(
                media_url,
                headers={"Authorization": f"Bearer {access_token[:10]}..."},  # Log partial token
                timeout=30,
            )

            logger.debug(
                "WhatsApp CDN response: status=%d, content_size=%d bytes, content_type=%s",
                media_resp.status_code,
                len(media_resp.content),
                media_resp.headers.get("content-type", "unknown"),
            )

            if media_resp.status_code != 200:
                logger.error(
                    "WhatsApp CDN error: status=%d, headers=%s",
                    media_resp.status_code,
                    dict(media_resp.headers),
                )
                return False, None, f"WhatsApp CDN error: {media_resp.status_code}"

            media_resp.raise_for_status()

            # Validate the downloaded audio
            logger.debug(
                "Downloaded %d bytes of audio data, validating...", len(media_resp.content)
            )
            is_valid, duration, error_msg = self.validate_audio_duration(media_resp.content)

            if is_valid:
                logger.info(
                    "WhatsApp audio validation successful: media_id=%s, duration=%.2fs",
                    media_id,
                    duration or 0,
                )
            else:
                logger.warning(
                    "WhatsApp audio validation failed: media_id=%s, error=%s, duration=%s",
                    media_id,
                    error_msg,
                    duration,
                )

            return is_valid, duration, error_msg

        except requests.exceptions.Timeout:
            logger.error("Timeout downloading WhatsApp media: media_id=%s", media_id)
            return False, None, "Timeout downloading audio"
        except requests.exceptions.RequestException as e:
            logger.error(
                "Network error downloading WhatsApp media: media_id=%s, error=%s",
                media_id,
                e,
                exc_info=True,
            )
            return False, None, f"Network error: {e}"
        except Exception as e:
            logger.error(
                "Unexpected error in WhatsApp media validation: media_id=%s, error=%s",
                media_id,
                e,
                exc_info=True,
            )
            # On error, reject to be safe (prevent unexpected costs)
            return False, None, f"Failed to download audio: {e}"
