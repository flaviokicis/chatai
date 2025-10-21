from __future__ import annotations

from typing import NotRequired, Required, TypedDict


class TwilioWebhookParams(TypedDict):
    From: Required[str]
    To: Required[str]
    Body: NotRequired[str]
    MessageSid: NotRequired[str]
    SmsMessageSid: NotRequired[str]
    MessageType: NotRequired[str]
    NumMedia: NotRequired[str]
    MediaUrl0: NotRequired[str]
    MediaContentType0: NotRequired[str]
    WhatsAppRawMessage: NotRequired[dict[str, object]]


class WhatsAppCloudAPIWebhook(TypedDict):
    object: Required[str]
    entry: Required[list[dict[str, object]]]


WebhookPayload = TwilioWebhookParams | WhatsAppCloudAPIWebhook

