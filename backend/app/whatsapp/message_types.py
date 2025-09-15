"""Typed message payload objects for WhatsApp structured data.

This module provides typed alternatives to raw dictionaries for WhatsApp message payloads,
enabling better validation, IDE support, and maintainability for buttons, templates, and other
structured message components.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class WhatsAppButton(BaseModel):
    """A WhatsApp interactive button."""

    id: str = Field(description="Unique button identifier")
    title: str = Field(max_length=20, description="Button display text")
    type: Literal["reply"] = Field(default="reply", description="Button type")

    @field_validator("title")
    @classmethod
    def validate_title_length(cls, v: str) -> str:
        """Validate button title length."""
        if len(v.strip()) == 0:
            raise ValueError("Button title cannot be empty")
        if len(v) > 20:
            raise ValueError("Button title cannot exceed 20 characters")
        return v.strip()


class WhatsAppListItem(BaseModel):
    """An item in a WhatsApp list message."""

    id: str = Field(description="Unique item identifier")
    title: str = Field(max_length=24, description="Item title")
    description: str | None = Field(default=None, max_length=72, description="Item description")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate item title."""
        if len(v.strip()) == 0:
            raise ValueError("List item title cannot be empty")
        return v.strip()


class WhatsAppListSection(BaseModel):
    """A section in a WhatsApp list message."""

    title: str | None = Field(default=None, max_length=24, description="Section title")
    rows: list[WhatsAppListItem] = Field(description="Items in this section")

    @field_validator("rows")
    @classmethod
    def validate_rows(cls, v: list[WhatsAppListItem]) -> list[WhatsAppListItem]:
        """Validate section rows."""
        if len(v) == 0:
            raise ValueError("Section must have at least one item")
        if len(v) > 10:
            raise ValueError("Section cannot have more than 10 items")
        return v


class WhatsAppInteractiveMessage(BaseModel):
    """WhatsApp interactive message with buttons or lists."""

    type: Literal["button", "list"] = Field(description="Interactive message type")
    header: str | None = Field(default=None, max_length=60, description="Message header")
    body: str = Field(max_length=1024, description="Message body text")
    footer: str | None = Field(default=None, max_length=60, description="Message footer")

    # Button-specific fields
    buttons: list[WhatsAppButton] | None = Field(default=None, description="Interactive buttons")

    # List-specific fields
    button_text: str | None = Field(default=None, max_length=20, description="List button text")
    sections: list[WhatsAppListSection] | None = Field(default=None, description="List sections")

    @field_validator("buttons")
    @classmethod
    def validate_buttons(cls, v: list[WhatsAppButton] | None) -> list[WhatsAppButton] | None:
        """Validate buttons."""
        if v is not None:
            if len(v) == 0:
                raise ValueError("Must have at least one button")
            if len(v) > 3:
                raise ValueError("Cannot have more than 3 buttons")
            # Check for duplicate IDs
            ids = [btn.id for btn in v]
            if len(ids) != len(set(ids)):
                raise ValueError("Button IDs must be unique")
        return v

    @field_validator("sections")
    @classmethod
    def validate_sections(
        cls, v: list[WhatsAppListSection] | None
    ) -> list[WhatsAppListSection] | None:
        """Validate list sections."""
        if v is not None:
            if len(v) == 0:
                raise ValueError("Must have at least one section")
            if len(v) > 10:
                raise ValueError("Cannot have more than 10 sections")
            # Check total items across all sections
            total_items = sum(len(section.rows) for section in v)
            if total_items > 10:
                raise ValueError("Cannot have more than 10 total items across all sections")
        return v


class WhatsAppTemplateParameter(BaseModel):
    """A parameter for WhatsApp template messages."""

    type: Literal["text", "currency", "date_time", "image", "document", "video"] = Field(
        description="Parameter type"
    )
    text: str | None = Field(default=None, description="Text content for text parameters")

    # Currency parameters
    fallback_value: str | None = Field(default=None, description="Fallback text for currency")
    code: str | None = Field(default=None, description="Currency code (e.g., USD)")
    amount_1000: int | None = Field(
        default=None, description="Amount in smallest currency unit * 1000"
    )

    # Date/time parameters
    fallback_value_datetime: str | None = Field(default=None, description="Fallback for datetime")

    # Media parameters
    link: str | None = Field(default=None, description="Media URL")
    caption: str | None = Field(default=None, description="Media caption")
    filename: str | None = Field(default=None, description="Document filename")


class WhatsAppTemplateComponent(BaseModel):
    """A component of a WhatsApp template message."""

    type: Literal["header", "body", "footer", "button"] = Field(description="Component type")
    sub_type: str | None = Field(default=None, description="Component subtype for buttons")
    index: int | None = Field(default=None, description="Component index for buttons")
    parameters: list[WhatsAppTemplateParameter] = Field(
        default_factory=list, description="Component parameters"
    )


class WhatsAppTemplateMessage(BaseModel):
    """WhatsApp template message."""

    name: str = Field(description="Template name")
    language_code: str = Field(default="en", description="Template language")
    components: list[WhatsAppTemplateComponent] = Field(
        default_factory=list, description="Template components"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate template name."""
        if not v.strip():
            raise ValueError("Template name cannot be empty")
        return v.strip().lower()


@dataclass(slots=True)
class WhatsAppMessagePayload:
    """Typed payload for WhatsApp messages stored in the database."""

    # Message identification
    message_type: str = "text"  # text, interactive, template, media, etc.

    # Interactive message data
    interactive: WhatsAppInteractiveMessage | None = None

    # Template message data
    template: WhatsAppTemplateMessage | None = None

    # Media information
    media_url: str | None = None
    media_type: str | None = None  # image, video, audio, document
    media_caption: str | None = None
    media_filename: str | None = None

    # Location data
    latitude: float | None = None
    longitude: float | None = None
    location_name: str | None = None
    location_address: str | None = None

    # Contact information
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None

    # Delivery and read receipts
    delivery_status: str = "pending"  # pending, sent, delivered, read, failed
    provider_message_id: str | None = None

    # Context and metadata
    quoted_message_id: str | None = None
    forwarded: bool = False

    # Additional structured data
    extra_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        result = {
            "message_type": self.message_type,
            "delivery_status": self.delivery_status,
            "forwarded": self.forwarded,
        }

        # Add non-None fields
        if self.interactive:
            result["interactive"] = self.interactive.model_dump()
        if self.template:
            result["template"] = self.template.model_dump()
        if self.media_url:
            result["media"] = {
                "url": self.media_url,
                "type": self.media_type,
                "caption": self.media_caption,
                "filename": self.media_filename,
            }
        if self.latitude is not None and self.longitude is not None:
            result["location"] = {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "name": self.location_name,
                "address": self.location_address,
            }
        if self.contact_name or self.contact_phone:
            result["contact"] = {
                "name": self.contact_name,
                "phone": self.contact_phone,
                "email": self.contact_email,
            }
        if self.quoted_message_id:
            result["quoted_message_id"] = self.quoted_message_id
        if self.provider_message_id:
            result["provider_message_id"] = self.provider_message_id
        if self.extra_data:
            result["extra"] = self.extra_data

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WhatsAppMessagePayload:
        """Create from dictionary (database retrieval)."""
        payload = cls(
            message_type=data.get("message_type", "text"),
            delivery_status=data.get("delivery_status", "pending"),
            forwarded=bool(data.get("forwarded", False)),
            quoted_message_id=data.get("quoted_message_id"),
            provider_message_id=data.get("provider_message_id"),
            extra_data=data.get("extra", {}),
        )

        # Parse interactive message
        if "interactive" in data:
            try:
                payload.interactive = WhatsAppInteractiveMessage.model_validate(data["interactive"])
            except Exception:
                # Fallback to storing in extra_data
                payload.extra_data["interactive_raw"] = data["interactive"]

        # Parse template message
        if "template" in data:
            try:
                payload.template = WhatsAppTemplateMessage.model_validate(data["template"])
            except Exception:
                # Fallback to storing in extra_data
                payload.extra_data["template_raw"] = data["template"]

        # Parse media information
        media_data = data.get("media", {})
        if isinstance(media_data, dict):
            payload.media_url = media_data.get("url")
            payload.media_type = media_data.get("type")
            payload.media_caption = media_data.get("caption")
            payload.media_filename = media_data.get("filename")

        # Parse location information
        location_data = data.get("location", {})
        if isinstance(location_data, dict):
            payload.latitude = location_data.get("latitude")
            payload.longitude = location_data.get("longitude")
            payload.location_name = location_data.get("name")
            payload.location_address = location_data.get("address")

        # Parse contact information
        contact_data = data.get("contact", {})
        if isinstance(contact_data, dict):
            payload.contact_name = contact_data.get("name")
            payload.contact_phone = contact_data.get("phone")
            payload.contact_email = contact_data.get("email")

        return payload


def create_button_message(
    body: str,
    buttons: list[tuple[str, str]],  # (id, title) pairs
    header: str | None = None,
    footer: str | None = None,
) -> WhatsAppMessagePayload:
    """Helper function to create a button message payload."""
    button_objects = [WhatsAppButton(id=btn_id, title=title) for btn_id, title in buttons]

    interactive = WhatsAppInteractiveMessage(
        type="button",
        body=body,
        header=header,
        footer=footer,
        buttons=button_objects,
    )

    return WhatsAppMessagePayload(
        message_type="interactive",
        interactive=interactive,
    )


def create_list_message(
    body: str,
    sections: list[
        tuple[str | None, list[tuple[str, str, str | None]]]
    ],  # (title, [(id, title, desc)])
    button_text: str = "Ver opções",
    header: str | None = None,
    footer: str | None = None,
) -> WhatsAppMessagePayload:
    """Helper function to create a list message payload."""
    section_objects = []
    for section_title, items in sections:
        item_objects = [
            WhatsAppListItem(id=item_id, title=title, description=desc)
            for item_id, title, desc in items
        ]
        section_objects.append(WhatsAppListSection(title=section_title, rows=item_objects))

    interactive = WhatsAppInteractiveMessage(
        type="list",
        body=body,
        header=header,
        footer=footer,
        button_text=button_text,
        sections=section_objects,
    )

    return WhatsAppMessagePayload(
        message_type="interactive",
        interactive=interactive,
    )
