from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.app_context import get_app_context
from app.core.llm import LLMClient
from app.main import app


def _patch_signature_validation(monkeypatch):
    # Bypass Twilio signature validation in tests, but still parse incoming params
    from app.whatsapp.twilio import TwilioWhatsAppHandler

    async def _ok(_self, request, _sig):  # type: ignore[no-untyped-def]
        content_type = request.headers.get("content-type", "").lower()
        if content_type.startswith("application/json"):
            raw_body = await request.body()
            try:
                return json.loads(raw_body.decode("utf-8"))
            except Exception:
                return {}
        form = await request.form()
        return {k: str(v) for k, v in form.items()}

    monkeypatch.setattr(TwilioWhatsAppHandler, "validate_and_parse", _ok)


@pytest.fixture
def config_with_limits(tmp_path):
    payload = {
        "default": {
            "enabled_agents": ["sales_qualifier"],
            "rate_limit": {
                "window_seconds": 60,
                "max_requests_per_user": 2,
                "max_requests_per_tenant": 50,
            },
            "channels": [
                {
                    "channel_type": "whatsapp",
                    "channel_id": "whatsapp:+14155238886",
                    "enabled_agents": ["sales_qualifier"],
                    "default_instance_id": "sq_default",
                    "agent_instances": [
                        {
                            "instance_id": "sq_default",
                            "agent_type": "sales_qualifier",
                            "params": {
                                "question_graph": {
                                    "global": [
                                        {
                                            "key": "intention",
                                            "prompt": "What are you looking to accomplish today?",
                                            "priority": 10,
                                        }
                                    ]
                                }
                            },
                            "handoff": {},
                        }
                    ],
                }
            ],
        }
    }
    payload["tenants"] = {"default": payload["default"]}
    path = tmp_path / "config_with_limits.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.integration
def test_rate_limiting_blocks_after_threshold(monkeypatch, config_with_limits):
    monkeypatch.setenv("CONFIG_JSON_PATH", str(config_with_limits))
    _patch_signature_validation(monkeypatch)

    client = TestClient(app)
    ctx = get_app_context(app)
    from app.config.loader import load_json_config

    ctx.config_provider = load_json_config(config_with_limits)
    # Ensure we use an in-memory limiter for deterministic tests
    from app.services.rate_limiter import InMemoryRateLimiterBackend, RateLimiter

    ctx.rate_limiter = RateLimiter(InMemoryRateLimiterBackend())

    # Simple LLM that does nothing special; we just want to send messages
    class NoopLLM(LLMClient):
        def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
            return {}

    ctx.llm = NoopLLM()

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550009999"
    to_num = "whatsapp:+14155238886"

    # First two should pass
    r1 = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "One more"},
        headers=headers,
    )
    assert r2.status_code == 200

    # Third within the window should be rate-limited
    r3 = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Again"},
        headers=headers,
    )
    assert r3.status_code == 200
    assert "message limit" in r3.text.lower()


@pytest.mark.integration  
def test_input_truncation_to_500_chars(monkeypatch, config_with_limits):
    monkeypatch.setenv("CONFIG_JSON_PATH", str(config_with_limits))
    _patch_signature_validation(monkeypatch)

    client = TestClient(app)
    ctx = get_app_context(app)
    from app.config.loader import load_json_config

    ctx.config_provider = load_json_config(config_with_limits)
    # Ensure we use an in-memory limiter for deterministic tests
    from app.services.rate_limiter import InMemoryRateLimiterBackend, RateLimiter

    ctx.rate_limiter = RateLimiter(InMemoryRateLimiterBackend())

    class CapturingLLM(LLMClient):
        def __init__(self) -> None:
            self.last_prompt = ""

        def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
            self.last_prompt = prompt
            return {}

    llm = CapturingLLM()
    ctx.llm = llm

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550008888"
    to_num = "whatsapp:+14155238886"
    long_body = "A" * 600

    # First request - should get initial question without LLM extraction
    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )

    # Second request with long body - should trigger LLM extraction with truncation
    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": long_body},
        headers=headers,
    )

    # The LLMFlowResponder prompt includes the user message verbatim
    assert "- User's message:" in llm.last_prompt
    idx = llm.last_prompt.find("- User's message:")
    assert idx >= 0
    snippet = llm.last_prompt[idx:].split("\n", 1)[0]
    # Extract the part after the colon and space
    latest = snippet.split(":", 1)[1].strip()
    assert len(latest) == 500
    assert latest == ("A" * 500)
