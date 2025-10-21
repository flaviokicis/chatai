from __future__ import annotations

from typing import Any, NewType, NotRequired, Required, TypedDict, TypeGuard

WhatsAppPhoneNumber = NewType("WhatsAppPhoneNumber", str)
TwilioMessageSid = NewType("TwilioMessageSid", str)


class ExtractedMessageData(TypedDict):
    sender_number: Required[str]
    receiver_number: Required[str]
    message_text: Required[str]
    message_id: Required[str]
    client_ip: Required[str]
    params: Required[dict[str, object]]
    is_aggregated: NotRequired[bool]
    original_message_count: NotRequired[int]
    skip_inbound_logging: NotRequired[bool]


def is_extracted_message_data(data: Any) -> TypeGuard[ExtractedMessageData]:
    """Runtime type guard for ExtractedMessageData.
    
    Use at boundaries where external data enters the system.
    """
    if not isinstance(data, dict):
        return False
    
    required_fields = {
        "sender_number": str,
        "receiver_number": str,
        "message_text": str,
        "message_id": str,
        "client_ip": str,
        "params": dict,
    }
    
    for field, expected_type in required_fields.items():
        if field not in data:
            return False
        if not isinstance(data[field], expected_type):
            return False
    
    return True


def validate_extracted_message_data(data: Any) -> ExtractedMessageData:
    """Validate and return ExtractedMessageData, raising on invalid data.
    
    Args:
        data: Data to validate
        
    Returns:
        Validated ExtractedMessageData
        
    Raises:
        ValueError: If data is invalid with specific error message
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")
    
    required_fields = ["sender_number", "receiver_number", "message_text", "message_id", "client_ip", "params"]
    missing = [f for f in required_fields if f not in data]
    
    if missing:
        raise ValueError(f"Missing required fields in message data: {missing}")
    
    for field in ["sender_number", "receiver_number", "message_text", "message_id", "client_ip"]:
        if not isinstance(data[field], str):
            raise ValueError(f"Field '{field}' must be str, got {type(data[field]).__name__}")
    
    if not isinstance(data["params"], dict):
        raise ValueError(f"Field 'params' must be dict, got {type(data['params']).__name__}")
    
    return data  # type: ignore[return-value]

