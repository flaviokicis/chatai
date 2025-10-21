"""Strongly typed message structures for WhatsApp and other channels.

This module provides type safety for message structures used throughout
the flow system, replacing dict[str, Any] with proper types.
"""

from typing import Literal, NotRequired, TypedDict


class WhatsAppMessage(TypedDict):
    """Strongly typed WhatsApp message structure.

    This replaces dict[str, Any] for message definitions,
    providing type safety and IDE support.
    """

    # Required fields
    text: str  # The message text content
    delay_ms: int  # Delay in milliseconds before sending

    # Optional fields for future enhancements
    media_url: NotRequired[str]  # URL for images/videos
    media_type: NotRequired[Literal["image", "video", "audio", "document"]]
    caption: NotRequired[str]  # Caption for media messages

    # Interactive elements (future)
    buttons: NotRequired[list[dict]]  # Quick reply buttons
    template_id: NotRequired[str]  # Template message ID
    template_params: NotRequired[dict[str, str]]  # Template parameters

    # Metadata
    message_id: NotRequired[str]  # Unique message identifier
    reply_to: NotRequired[str]  # ID of message being replied to
