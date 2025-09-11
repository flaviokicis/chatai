"""Updated WhatsApp simulated flow tests using database-driven approach."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.app_context import get_app_context
from app.core.llm import LLMClient
from app.main import app
from tests.webhook_test_utils import (
    _patch_signature_validation,
    create_paths_flow,
    create_sales_qualifier_flow,
    create_test_tenant_with_flow,
)


class SeqLLM(LLMClient):
    """Deterministic LLM for tests: returns each result sequentially."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = results
        self._i = 0

    def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
        if self._i < len(self._results):
            res = self._results[self._i]
            self._i += 1
            return res
        return {}


@pytest.mark.integration
def test_whatsapp_like_flow(monkeypatch):
    """Test basic WhatsApp flow with database setup."""
    # Force use of Twilio adapter
    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")

    # Create database records
    flow_definition = create_sales_qualifier_flow()
    tenant, channel, flow, to_num = create_test_tenant_with_flow(
        flow_definition=flow_definition,
        flow_name="Sales Qualifier"
    )

    # Bypass signature validation
    _patch_signature_validation(monkeypatch)

    client = TestClient(app)

    # Setup app context with deterministic LLM
    ctx = get_app_context(app)
    ctx.llm = SeqLLM([
        {"__tool_name__": "UpdateAnswers", "updates": {"intention": "buy leds"}},
    ])

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550001111"

    # Turn 1: user greets, LLM updates intention, should move to budget question
    r1 = client.post(
        "/webhooks/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )
    assert r1.status_code == 200
    txt1 = r1.text
    # Since LLM immediately provides intention="buy leds", flow moves to budget question
    assert (
        "Você tem alguma faixa de orçamento em mente?" in txt1
        or "Do you have a budget range in mind?" in txt1
    )


@pytest.mark.skip(reason="Complex flow features (PathSelection, Escalation) not implemented in current flow engine")
@pytest.mark.integration
def test_ambiguous_paths_escalate_to_human(monkeypatch):
    """Test that ambiguous paths escalate to human with database setup."""
    # Force use of Twilio adapter
    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")

    # Create database records with paths flow
    flow_definition = create_paths_flow(lock_threshold=2)
    tenant, channel, flow, to_num = create_test_tenant_with_flow(
        flow_definition=flow_definition,
        flow_name="Paths Flow"
    )

    # Bypass signature validation
    _patch_signature_validation(monkeypatch)

    client = TestClient(app)

    # LLM sequence answers the three global fields and nothing else
    class ThreeStepLLM(LLMClient):
        def __init__(self) -> None:
            self._i = 0

        def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
            # If asked to select path, always choose none in this test
            if any(getattr(t, "__name__", "") == "SelectFlowPath" for t in tools):
                return {"__tool_name__": "SelectFlowPath", "path": None}
            self._i += 1
            if self._i == 1:
                return {"__tool_name__": "UpdateAnswers", "updates": {"intention": "buy leds"}}
            if self._i == 2:
                return {"__tool_name__": "UpdateAnswers", "updates": {"budget": "10k"}}
            if self._i == 3:
                return {"__tool_name__": "UpdateAnswers", "updates": {"timeframe": "3 months"}}
            return {}

    ctx = get_app_context(app)
    ctx.llm = ThreeStepLLM()

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550002222"

    # Turn 1
    client.post(
        "/webhooks/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )
    # Turn 2
    client.post(
        "/webhooks/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "I want to buy LEDs"},
        headers=headers,
    )
    # Turn 3
    client.post(
        "/webhooks/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "10 thou"},
        headers=headers,
    )
    # Turn 4 should escalate since global is complete and no path locked
    r4 = client.post(
        "/webhooks/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "in a few months"},
        headers=headers,
    )
    assert r4.status_code == 200
    assert "Transferindo você para um atendente humano" in r4.text


@pytest.mark.skip(reason="Complex flow features (PathSelection, Escalation) not implemented in current flow engine")
@pytest.mark.integration
def test_paths_selection_and_questions_flow(monkeypatch):
    """Test path selection and questions flow with database setup."""
    # Force use of Twilio adapter
    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")

    # Create database records with paths flow (immediate lock)
    flow_definition = create_paths_flow(lock_threshold=1)
    tenant, channel, flow, to_num = create_test_tenant_with_flow(
        flow_definition=flow_definition,
        flow_name="Paths Lock Flow"
    )

    # Bypass signature validation
    _patch_signature_validation(monkeypatch)

    client = TestClient(app)

    # LLM: intention first, then court_type
    class PathLLM(LLMClient):
        def __init__(self) -> None:
            self._i = 0

        def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
            # When asked to select a path, immediately choose tennis_court
            if any(getattr(t, "__name__", "") == "SelectFlowPath" for t in tools):
                return {"__tool_name__": "SelectFlowPath", "path": "tennis_court"}
            self._i += 1
            if self._i == 1:
                return {
                    "__tool_name__": "UpdateAnswers",
                    "updates": {"intention": "tennis court"},
                }
            if self._i == 2:
                return {"__tool_name__": "UpdateAnswers", "updates": {"court_type": "indoor"}}
            return {}

    ctx = get_app_context(app)
    ctx.llm = PathLLM()

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550003333"

    # Turn 1: get intention question
    r1 = client.post(
        "/webhooks/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )
    assert r1.status_code == 200
    assert "What are you looking to accomplish today?" in r1.text

    # Turn 2: answer with tennis, should select path and ask court_type
    r2 = client.post(
        "/webhooks/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "I need a tennis court"},
        headers=headers,
    )
    assert r2.status_code == 200
    assert "Is it indoor or outdoor?" in r2.text

    # Turn 3: answer court_type, should ask budget (next global)
    r3 = client.post(
        "/webhooks/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "indoor please"},
        headers=headers,
    )
    assert r3.status_code == 200
    assert "Do you have a budget range in mind?" in r3.text
