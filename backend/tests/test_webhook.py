"""Test the refactored webhook with proper database setup."""

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
    from app.whatsapp.twilio_adapter import TwilioWhatsAppAdapter

    async def _ok(_self, request, _sig):
        form = await request.form()
        return {k: str(v) for k, v in form.items()}

    monkeypatch.setattr(TwilioWhatsAppAdapter, "validate_and_parse", _ok)


def create_test_tenant_and_flow():
    """Create a test tenant with flow in database."""
    import uuid
    test_id = str(uuid.uuid4())[:8]

    session = create_session()

    try:
        # Create tenant
        tenant = create_tenant_with_config(
            session,
            first_name="Test",
            last_name="User",
            email=f"test-{test_id}@example.com",
            project_description="Test project",
            target_audience="Test audience",
            communication_style="Test style"
        )

        # Create WhatsApp channel with unique number
        test_number = f"whatsapp:+1666{test_id[:4]}{test_id[4:8]}"
        channel = create_channel_instance(
            session,
            tenant_id=tenant.id,
            channel_type=ChannelType.whatsapp,
            identifier=test_number,
            phone_number=test_number.replace("whatsapp:", ""),
            extra={"display_name": "Test"}
        )

        # Create simple test flow
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
                    "reason": "Thank you!"
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
        return tenant, channel, flow, test_number

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_refactored_webhook_basic_flow(monkeypatch):
    """Test that the refactored webhook works with proper database setup."""
    # Force use of Twilio adapter
    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")

    # Create test data
    tenant, channel, flow, to_num = create_test_tenant_and_flow()

    # Bypass signature validation
    _patch_signature_validation(monkeypatch)

    client = TestClient(app)

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550001111"

    # Test basic webhook processing
    response = client.post(
        "/webhooks/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )

    assert response.status_code == 200
    # Should not get the "not configured" error
    assert "não está configurado" not in response.text
    # Should get some kind of response (flow processing)
    assert len(response.text) > 0


def test_refactored_webhook_no_config_fallback(monkeypatch):
    """Test that the refactored webhook handles missing config gracefully."""
    # Force use of Twilio adapter
    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")

    # Bypass signature validation
    _patch_signature_validation(monkeypatch)

    client = TestClient(app)

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550009999"
    to_num = "whatsapp:+19999999999"  # Non-existent number

    # Test webhook with non-existent config
    response = client.post(
        "/webhooks/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )

    assert response.status_code == 200
    # Should get the "not configured" error message
    assert "não está configurado" in response.text


def test_audio_message_transcription(monkeypatch):
    """Ensure audio messages are transcribed and processed."""
    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
    tenant, channel, flow, to_num = create_test_tenant_and_flow()
    _patch_signature_validation(monkeypatch)

    # Patch transcription service to avoid external calls
    from app.services.speech_to_text_service import SpeechToTextService

    called: dict[str, str] = {}

    def fake_transcribe(self, media_url: str) -> str:
        called["url"] = media_url
        return "transcribed audio"

    monkeypatch.setattr(SpeechToTextService, "transcribe_twilio_media", fake_transcribe)

    client = TestClient(app)
    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550001234"

    response = client.post(
        "/webhooks/whatsapp",
        data={
            "From": from_num,
            "To": to_num,
            "NumMedia": "1",
            "MediaUrl0": "http://example.com/audio.ogg",
            "MediaContentType0": "audio/ogg",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert called
    assert len(response.text) > 0
