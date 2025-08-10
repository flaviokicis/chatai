from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from app.config.loader import load_json_config


def write_tmp_json(tmp_path: Path, data: dict) -> str:
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_load_default_minimal(tmp_path: Path) -> None:
    path = write_tmp_json(tmp_path, {"default": {"enabled_agents": ["sales_qualifier"]}})
    provider = load_json_config(path)
    cfg = provider.get_tenant_config("any")
    assert cfg.enabled_agents == ["sales_qualifier"]
    assert cfg.channels == []


def test_load_with_channel_and_instance(tmp_path: Path) -> None:
    data = {
        "default": {
            "enabled_agents": ["sales_qualifier"],
            "channels": [
                {
                    "channel_type": "whatsapp",
                    "channel_id": "whatsapp:+15551112222",
                    "enabled_agents": ["sales_qualifier"],
                    "default_instance_id": "sq_default",
                    "agent_instances": [
                        {
                            "instance_id": "sq_default",
                            "agent_type": "sales_qualifier",
                            "params": {
                                "question_graph": [
                                    {
                                        "key": "intention",
                                        "prompt": "What is your intention?",
                                        "priority": 10,
                                    }
                                ]
                            },
                            "handoff": {"target": "sales_slack"},
                        }
                    ],
                }
            ],
        }
    }
    path = write_tmp_json(tmp_path, data)
    provider = load_json_config(path)
    cfg = provider.get_tenant_config("any")
    assert len(cfg.channels) == 1
    ch = provider.get_channel_config("any", "whatsapp", "whatsapp:+15551112222")
    assert ch is not None
    assert ch.default_instance_id == "sq_default"
    assert ch.agent_instances
    assert ch.agent_instances[0].agent_type == "sales_qualifier"


@pytest.mark.parametrize(
    ("payload", "err"),
    [
        ({"default": []}, "'default' must be an object"),
        ({"tenants": []}, "'tenants' must be an object"),
    ],
)
def test_validation_errors(tmp_path: Path, payload: dict, err: str) -> None:
    path = write_tmp_json(tmp_path, payload)
    with pytest.raises(ValueError, match=re.escape(err)):
        load_json_config(path)
