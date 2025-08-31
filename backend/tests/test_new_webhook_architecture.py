#!/usr/bin/env python3
"""
Tests for the new database-driven webhook architecture.

These tests create actual database records (tenant, channel, flows) instead of 
relying on hardcoded JSON configuration files.
"""


import pytest
from fastapi.testclient import TestClient

from app.db.models import ChannelType
from app.db.repository import (
    create_channel_instance,
    create_flow,
    create_tenant_with_config,
)
from app.db.session import create_session
from app.main import app


def _patch_signature_validation(monkeypatch):
    """Bypass Twilio signature validation in tests."""
    from app.whatsapp.twilio import TwilioWhatsAppHandler

    async def _ok(_self, request, _sig):
        form = await request.form()
        return {k: str(v) for k, v in form.items()}

    monkeypatch.setattr(TwilioWhatsAppHandler, "validate_and_parse", _ok)


def create_test_tenant_and_flow():
    """Create a test tenant with dental flow in database."""
    import uuid
    test_id = str(uuid.uuid4())[:8]  # Short unique ID

    session = create_session()

    try:
        # Create tenant
        tenant = create_tenant_with_config(
            session,
            first_name="Dr. Test",
            last_name="Dentist",
            email=f"test-{test_id}@example.com",
            project_description="Test dental clinic",
            target_audience="Test patients",
            communication_style="Test friendly style"
        )

        # Create WhatsApp channel with unique identifier
        test_number = f"whatsapp:+1555{test_id[:4]}{test_id[4:8]}"
        channel = create_channel_instance(
            session,
            tenant_id=tenant.id,
            channel_type=ChannelType.whatsapp,
            identifier=test_number,
            phone_number=test_number.replace("whatsapp:", ""),
            extra={"display_name": "Test Clinic"}
        )

        # Create simple test flow with correct schema
        flow_definition = {
            "schema_version": "v2",
            "id": "test_flow",
            "entry": "welcome",
            "nodes": [
                {
                    "id": "welcome",
                    "kind": "Question",
                    "key": "intention",
                    "prompt": "What are you looking to accomplish today?"
                },
                {
                    "id": "complete",
                    "kind": "Terminal",
                    "reason": "Thank you for your interest!"
                }
            ],
            "edges": [
                {
                    "source": "welcome",
                    "target": "complete",
                    "guard": {"fn": "answers_has", "args": {"key": "intention"}},
                    "priority": 0
                }
            ]
        }

        flow = create_flow(
            session,
            tenant_id=tenant.id,
            channel_instance_id=channel.id,
            name="Test Flow",
            flow_id="test_flow_v1",
            definition=flow_definition
        )

        session.commit()
        return tenant.id, channel.id, flow.id, test_number

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


@pytest.mark.integration
def test_database_driven_webhook_flow(monkeypatch):
    """Test that webhook correctly loads flow from database and processes messages."""

    # Force use of Twilio adapter for form data tests
    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
    _patch_signature_validation(monkeypatch)

    # Create test data in database
    tenant_id, channel_id, flow_id, test_number = create_test_tenant_and_flow()

    client = TestClient(app)

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550001111"
    to_num = test_number  # Use unique test channel

    # Turn 1: Send greeting, should get first question
    response = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )

    assert response.status_code == 200
    assert "What are you looking to accomplish today?" in response.text

    # Turn 2: Answer question, should get completion message
    response2 = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "I need dental help"},
        headers=headers,
    )

    assert response2.status_code == 200
    # Terminal nodes return their reason field as the message
    assert "Thank you for your interest!" in response2.text


@pytest.mark.integration
def test_channel_not_found_error(monkeypatch):
    """Test that webhook returns appropriate error for unknown channels."""

    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
    _patch_signature_validation(monkeypatch)

    client = TestClient(app)

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550001111"
    to_num = "whatsapp:+99999999999"  # Non-existent channel

    response = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )

    assert response.status_code == 200
    assert "não está configurado" in response.text
