"""Tests for training mode functionality."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.llm import LLMClient
from app.db.models import ChannelType
from app.db.repository import (
    create_channel_instance,
    create_flow,
    create_tenant_with_config,
)
from app.db.session import create_session
from app.main import app
from app.services.training_mode_service import TrainingModeService


class MockLLMForTraining(LLMClient):
    """Mock LLM that can trigger EnterTrainingMode tool."""

    def __init__(self, should_enter_training: bool = False):
        self.should_enter_training = should_enter_training
        self.call_count = 0

    def extract(self, prompt: str, tools: list[type]) -> dict[str, Any]:  # type: ignore[override]
        self.call_count += 1

        # Check if EnterTrainingMode tool is available and we should trigger it
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        if self.should_enter_training and "EnterTrainingMode" in tool_names:
            return {
                "__tool_name__": "EnterTrainingMode",
                "reason": "explicit_user_request",
                "reasoning": "User explicitly requested training mode activation"
            }

        # Default flow behavior - extract answers
        return {
            "__tool_name__": "UpdateAnswersFlow",
            "updates": {"name": "Test User"} if "name" in prompt.lower() else {"intention": "testing"},
            "validated": True,
            "reasoning": "Extracted user information from message"
        }


def _patch_signature_validation(monkeypatch):
    """Bypass Twilio signature validation in tests."""
    from app.whatsapp.twilio_adapter import TwilioWhatsAppAdapter

    async def _ok(_self, request, _sig):
        form = await request.form()
        return {k: str(v) for k, v in form.items()}

    monkeypatch.setattr(TwilioWhatsAppAdapter, "validate_and_parse", _ok)


def create_test_flow_with_training():
    """Create a test flow with training password."""
    test_id = str(uuid.uuid4())[:8]

    session = create_session()
    try:
        tenant = create_tenant_with_config(
            session,
            first_name="Training",
            last_name="Tester",
            email=f"training-{test_id}@example.com",
            project_description="Training test clinic",
            target_audience="Test users",
            communication_style="Friendly"
        )

        test_number = f"whatsapp:+1777{test_id[:4]}{test_id[4:8]}"
        channel = create_channel_instance(
            session,
            tenant_id=tenant.id,
            channel_type=ChannelType.whatsapp,
            identifier=test_number,
            phone_number=test_number.replace("whatsapp:", ""),
        )

        flow_definition = {
            "schema_version": "v2",
            "id": "training_flow",
            "entry": "greeting",
            "nodes": [
                {
                    "id": "greeting",
                    "kind": "Question",
                    "key": "name",
                    "prompt": "What's your name?"
                },
                {
                    "id": "done",
                    "kind": "Terminal",
                    "reason": "Thanks for testing!"
                }
            ],
            "edges": [
                {
                    "source": "greeting",
                    "target": "done",
                    "guard": {"fn": "answers_has", "args": {"key": "name"}},
                    "priority": 0
                }
            ]
        }

        flow = create_flow(
            session,
            tenant_id=tenant.id,
            channel_instance_id=channel.id,
            name="Training Flow",
            flow_id="training_v1",
            definition=flow_definition
        )

        # Set training password
        flow.training_password = "5678"

        session.commit()
        return tenant.id, channel.id, flow.id, test_number

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def test_enter_training_mode_tool():
    """Test that EnterTrainingMode tool can be called by LLM."""
    from app.flow_core.tool_schemas import EnterTrainingMode

    # Verify tool schema
    tool = EnterTrainingMode(reason="explicit_user_request")
    assert tool.reason == "explicit_user_request"

    # Test with mock LLM
    mock_llm = MockLLMForTraining(should_enter_training=True)
    result = mock_llm.extract("User wants training mode", [EnterTrainingMode])

    assert result["__tool_name__"] == "EnterTrainingMode"
    assert result["reason"] == "explicit_user_request"


def test_training_mode_password_flow():
    """Test password validation logic in isolation."""
    # Mock dependencies
    mock_session = MagicMock()
    mock_app_context = MagicMock()
    mock_store = MagicMock()
    mock_app_context.store = mock_store

    # Mock thread and flow
    mock_thread = MagicMock()
    mock_thread.extra = {}
    mock_flow = MagicMock()
    mock_flow.id = "test-flow-id"
    mock_flow.training_password = "5678"

    service = TrainingModeService(mock_session, mock_app_context)

    # Start handshake
    prompt = service.start_handshake(
        mock_thread,
        mock_flow,
        user_id="test-user",
        flow_session_key="test-session"
    )
    assert prompt == "Para entrar no modo treino, informe a senha."
    assert mock_thread.extra["awaiting_training_password"] is True

    # Test correct password
    mock_thread.extra = {"awaiting_training_password": True, "pending_training_flow_id": "test-flow-id"}
    success, reply = service.validate_password(
        mock_thread,
        mock_flow,
        "5678",
        user_id="test-user",
        flow_session_key="test-session"
    )
    assert success is True
    assert "Modo treino ativado" in reply

    # Test wrong password
    mock_thread.extra = {"awaiting_training_password": True, "pending_training_flow_id": "test-flow-id"}
    success, reply = service.validate_password(
        mock_thread,
        mock_flow,
        "1111",
        user_id="test-user",
        flow_session_key="test-session"
    )
    assert success is True
    assert "Senha incorreta" in reply

    # Test non-numeric input (should reset)
    mock_thread.extra = {"awaiting_training_password": True, "pending_training_flow_id": "test-flow-id"}
    success, reply = service.validate_password(
        mock_thread,
        mock_flow,
        "hello world",
        user_id="test-user",
        flow_session_key="test-session"
    )
    assert success is True
    assert "Que tal começarmos de novo" in reply


@pytest.mark.integration
def test_training_password_validation(monkeypatch):
    """Test password validation flow with attempts and reset."""

    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
    _patch_signature_validation(monkeypatch)

    tenant_id, channel_id, flow_id, test_number = create_test_flow_with_training()

    client = TestClient(app)
    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550003333"

    # Step 1: Trigger training mode
    response = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "modo treino"},
        headers=headers,
    )
    assert response.status_code == 200
    assert "Para entrar no modo treino" in response.text

    # Step 2: Wrong password (numeric)
    response = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "1111"},
        headers=headers,
    )
    assert response.status_code == 200
    assert "Senha incorreta" in response.text

    # Step 3: Non-numeric input (should reset)
    response = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "hello world"},
        headers=headers,
    )
    assert response.status_code == 200
    assert "Que tal começarmos de novo" in response.text

    # Step 4: Trigger again and provide correct password
    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "modo treino"},
        headers=headers,
    )

    response = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "5678"},
        headers=headers,
    )
    assert response.status_code == 200
    assert "Modo treino ativado" in response.text


@pytest.mark.integration
def test_training_password_three_attempts(monkeypatch):
    """Test that 3 wrong password attempts trigger reset."""

    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
    _patch_signature_validation(monkeypatch)

    tenant_id, channel_id, flow_id, test_number = create_test_flow_with_training()

    client = TestClient(app)
    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550004444"

    # Trigger training mode
    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "modo treino"},
        headers=headers,
    )

    # Three wrong attempts
    for i in range(3):
        response = client.post(
            "/webhooks/twilio/whatsapp",
            data={"From": from_num, "To": test_number, "Body": "9999"},
            headers=headers,
        )
        if i < 2:
            assert "Senha incorreta" in response.text
        else:
            assert "Que tal começarmos de novo" in response.text


def test_training_mode_service_unit():
    """Unit test for TrainingModeService logic."""

    # Mock dependencies
    mock_session = MagicMock()
    mock_app_context = MagicMock()
    mock_store = MagicMock()
    mock_app_context.store = mock_store

    service = TrainingModeService(mock_session, mock_app_context)

    # Test trigger detection
    assert service.is_trigger("modo treino")
    assert service.is_trigger("ativar modo de treinamento")
    assert service.is_trigger("comecar treino")  # without cedilla
    assert not service.is_trigger("hello world")
    assert not service.is_trigger("treino casual mention")

    # Test normalization
    assert service._norm("  MODO TREINO  ") == "modo treino"
    assert service._norm("Ativar Modo De Treinamento") == "ativar modo de treinamento"


@pytest.mark.integration
def test_training_mode_flow_editing(monkeypatch):
    """Test that training mode routes to flow modification tools."""

    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
    _patch_signature_validation(monkeypatch)

    tenant_id, channel_id, flow_id, test_number = create_test_flow_with_training()

    client = TestClient(app)
    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550005555"

    # Enter training mode
    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "modo treino"},
        headers=headers,
    )

    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "5678"},
        headers=headers,
    )

    # Send flow modification instruction
    response = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "Change the greeting prompt to 'Hello, what is your full name?'"},
        headers=headers,
    )

    assert response.status_code == 200
    # Should get a response about the modification (exact text varies)
    assert len(response.text) > 10  # Some meaningful response


@pytest.mark.integration
def test_training_mode_simulation(monkeypatch):
    """Test that simulation triggers work in training mode."""

    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
    _patch_signature_validation(monkeypatch)

    tenant_id, channel_id, flow_id, test_number = create_test_flow_with_training()

    client = TestClient(app)
    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550006666"

    # Enter training mode
    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "modo treino"},
        headers=headers,
    )

    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "5678"},
        headers=headers,
    )

    # Test simulation
    response = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "Simular: My name is John"},
        headers=headers,
    )

    assert response.status_code == 200
    # Should simulate the flow response (exact text varies based on flow)
    assert len(response.text) > 5  # Some meaningful response

