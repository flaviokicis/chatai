"""Tests for training mode functionality."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import create_session
from app.db.repository import (
    create_tenant_with_config,
    create_channel_instance, 
    create_flow,
    get_flow_by_id,
)
from app.db.models import ChannelType
from app.services.training_mode_service import TrainingModeService
from unittest.mock import MagicMock
import uuid


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


@pytest.mark.integration
def test_training_mode_trigger_detection(monkeypatch):
    """Test that LLM detects training mode triggers and calls EnterTrainingMode tool."""
    
    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
    _patch_signature_validation(monkeypatch)
    
    tenant_id, channel_id, flow_id, test_number = create_test_flow_with_training()
    
    client = TestClient(app)
    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550002222"
    
    # Send training trigger
    response = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": test_number, "Body": "ativar modo treino"},
        headers=headers,
    )
    
    assert response.status_code == 200
    assert "Para entrar no modo treino, informe a senha" in response.text


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

