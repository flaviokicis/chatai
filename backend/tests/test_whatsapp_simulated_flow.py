from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config.loader import load_json_config
from app.core.app_context import get_app_context
from app.core.llm import LLMClient
from app.main import app


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


@pytest.fixture
def config_json(tmp_path):
    payload = {
        "default": {
            "enabled_agents": ["sales_qualifier"],
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
                                        },
                                        {
                                            "key": "budget",
                                            "prompt": "Do you have a budget range in mind?",
                                            "priority": 90,
                                        },
                                        {
                                            "key": "timeframe",
                                            "prompt": "What is your ideal timeline?",
                                            "priority": 100,
                                        },
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
    # Ensure top-level 'tenants' mirrors default so provider lookups succeed either way
    payload["tenants"] = {
        "default": payload["default"],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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


def test_whatsapp_like_flow(monkeypatch, config_json):
    # Ensure app startup loads our test config
    monkeypatch.setenv("CONFIG_JSON_PATH", str(config_json))

    _patch_signature_validation(monkeypatch)

    client = TestClient(app)

    # Ensure config provider is loaded from our temp file even if startup used another
    ctx = get_app_context(app)
    ctx.config_provider = load_json_config(config_json)

    # Replace LLM with deterministic sequence: first no updates, then intention update
    ctx.llm = SeqLLM(
        [
            {},
            {"__tool_name__": "UpdateAnswers", "updates": {"intention": "buy leds"}},
        ]
    )

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550001111"
    to_num = "whatsapp:+14155238886"

    # Turn 1: user greets, should ask the first question (intention)
    r1 = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )
    assert r1.status_code == 200
    txt1 = r1.text
    assert "What are you looking to accomplish today?" in txt1

    # Turn 2: user provides intention; should move to next question (budget)
    r2 = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "I want to buy LEDs"},
        headers=headers,
    )
    assert r2.status_code == 200
    txt2 = r2.text
    assert "Do you have a budget range in mind?" in txt2

    # Verify state persisted for this user and agent
    state = ctx.store.load(from_num, "sales_qualifier")
    assert isinstance(state, dict)
    assert state.get("answers", {}).get("intention") == "buy leds"


def test_ambiguous_paths_escalate_to_human(monkeypatch, tmp_path):
    # Build config with two paths and entry predicates that won't match our inputs
    cfg = {
        "default": {
            "enabled_agents": ["sales_qualifier"],
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
                                        },
                                        {
                                            "key": "budget",
                                            "prompt": "Do you have a budget range in mind?",
                                            "priority": 90,
                                        },
                                        {
                                            "key": "timeframe",
                                            "prompt": "What is your ideal timeline?",
                                            "priority": 100,
                                        },
                                    ],
                                    "paths": {
                                        "tennis_court": {
                                            "entry_predicates": [
                                                {
                                                    "type": "keyword",
                                                    "any": ["tennis", "court", "racket"],
                                                },
                                                {"type": "regex", "pattern": "(tennis|court)\\b"},
                                            ],
                                            "questions": [
                                                {
                                                    "key": "court_type",
                                                    "prompt": "Is it indoor or outdoor?",
                                                    "priority": 20,
                                                }
                                            ],
                                        },
                                        "soccer_court": {
                                            "entry_predicates": [
                                                {
                                                    "type": "keyword",
                                                    "any": ["soccer", "football", "pitch"],
                                                }
                                            ],
                                            "questions": [
                                                {
                                                    "key": "field_size",
                                                    "prompt": "Approximate field size?",
                                                    "priority": 20,
                                                }
                                            ],
                                        },
                                    },
                                    "path_selection": {
                                        "lock_threshold": 2,
                                        "allow_switch_before_lock": True,
                                    },
                                }
                            },
                            "handoff": {},
                        }
                    ],
                }
            ],
        }
    }
    cfg["tenants"] = {"default": cfg["default"]}
    path = tmp_path / "config_paths.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    # Bypass Twilio signature and parse form
    _patch_signature_validation(monkeypatch)

    # Ensure app uses this config
    monkeypatch.setenv("CONFIG_JSON_PATH", str(path))
    client = TestClient(app)
    ctx = get_app_context(app)
    from app.config.loader import load_json_config

    ctx.config_provider = load_json_config(path)

    # LLM sequence answers the three global fields and nothing else
    from app.core.llm import LLMClient

    class ThreeStepLLM(LLMClient):
        def __init__(self) -> None:
            self._i = 0

        def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
            # If asked to select path, always choose none in this test
            if any(getattr(t, "__name__", "") == "SelectPath" for t in tools):
                return {"__tool_name__": "SelectPath", "path": None}
            self._i += 1
            if self._i == 1:
                return {}
            if self._i == 2:
                return {"__tool_name__": "UpdateAnswers", "updates": {"intention": "buy leds"}}
            if self._i == 3:
                return {"__tool_name__": "UpdateAnswers", "updates": {"budget": "10k"}}
            if self._i == 4:
                return {"__tool_name__": "UpdateAnswers", "updates": {"timeframe": "3 months"}}
            return {}

    ctx.llm = ThreeStepLLM()

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550002222"
    to_num = "whatsapp:+14155238886"

    # Turn 1
    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )
    # Turn 2
    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "I want to buy LEDs"},
        headers=headers,
    )
    # Turn 3
    client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "10 thou"},
        headers=headers,
    )
    # Turn 4 should escalate since global is complete and no path locked
    r4 = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "in a few months"},
        headers=headers,
    )
    assert r4.status_code == 200
    assert "Transferring" in r4.text
    # And active path should remain unset in state
    state = ctx.store.load(from_num, "sales_qualifier")
    assert isinstance(state, dict)
    assert state.get("active_path") in (None, "")


def test_paths_selection_and_questions_flow(monkeypatch, tmp_path):
    # Config with paths and immediate lock upon first predicate match
    cfg = {
        "default": {
            "enabled_agents": ["sales_qualifier"],
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
                                        },
                                        {
                                            "key": "budget",
                                            "prompt": "Do you have a budget range in mind?",
                                            "priority": 90,
                                        },
                                        {
                                            "key": "timeframe",
                                            "prompt": "What is your ideal timeline?",
                                            "priority": 100,
                                        },
                                    ],
                                    "paths": {
                                        "tennis_court": {
                                            "entry_predicates": [
                                                {"type": "keyword", "any": ["tennis", "court"]}
                                            ],
                                            "questions": [
                                                {
                                                    "key": "court_type",
                                                    "prompt": "Is it indoor or outdoor?",
                                                    "priority": 20,
                                                }
                                            ],
                                        },
                                        "soccer_court": {
                                            "entry_predicates": [
                                                {
                                                    "type": "keyword",
                                                    "any": ["soccer", "football", "pitch"],
                                                }
                                            ],
                                            "questions": [
                                                {
                                                    "key": "field_size",
                                                    "prompt": "Approximate field size?",
                                                    "priority": 20,
                                                }
                                            ],
                                        },
                                    },
                                    "path_selection": {
                                        "lock_threshold": 1,
                                        "allow_switch_before_lock": True,
                                    },
                                }
                            },
                            "handoff": {},
                        }
                    ],
                }
            ],
        }
    }
    cfg["tenants"] = {"default": cfg["default"]}
    path = tmp_path / "config_paths_lock1.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    _patch_signature_validation(monkeypatch)
    monkeypatch.setenv("CONFIG_JSON_PATH", str(path))
    client = TestClient(app)
    ctx = get_app_context(app)
    from app.config.loader import load_json_config

    ctx.config_provider = load_json_config(path)

    # LLM: intention first, then court_type
    class PathLLM(LLMClient):
        def __init__(self) -> None:
            self._i = 0

        def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]:  # type: ignore[override]
            # When asked to select a path, immediately choose tennis_court
            if any(getattr(t, "__name__", "") == "SelectPath" for t in tools):
                return {"__tool_name__": "SelectPath", "path": "tennis_court"}
            self._i += 1
            if self._i == 1:
                return {}
            if self._i == 2:
                return {"__tool_name__": "UpdateAnswers", "updates": {"intention": "tennis court"}}
            if self._i == 3:
                return {"__tool_name__": "UpdateAnswers", "updates": {"court_type": "indoor"}}
            return {}

    ctx.llm = PathLLM()

    headers = {"X-Twilio-Signature": "test"}
    from_num = "whatsapp:+15550003333"
    to_num = "whatsapp:+14155238886"

    # Turn 1: get intention question
    r1 = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "Hello"},
        headers=headers,
    )
    assert r1.status_code == 200
    assert "What are you looking to accomplish today?" in r1.text

    # Turn 2: mention tennis; locks tennis path; expect path question next
    r2 = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "I want tennis court LEDs"},
        headers=headers,
    )
    assert r2.status_code == 200
    assert "Is it indoor or outdoor?" in r2.text

    # Turn 3: answer path question; expect to proceed to next global question (budget)
    r3 = client.post(
        "/webhooks/twilio/whatsapp",
        data={"From": from_num, "To": to_num, "Body": "indoor"},
        headers=headers,
    )
    assert r3.status_code == 200
    assert "Do you have a budget range in mind?" in r3.text

    # Verify state contains path and court_type
    state = ctx.store.load(from_num, "sales_qualifier")
    assert isinstance(state, dict)
    assert state.get("active_path") == "tennis_court"
    assert state.get("answers", {}).get("court_type") == "indoor"
