from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .provider import ConfigProvider, JSONConfigProvider


def load_json_config(path: str | Path) -> ConfigProvider:
    p = Path(path)
    if not p.exists():
        # minimal default config
        data: dict[str, Any] = {
            "default": {
                "enabled_agents": ["sales_qualifier"],
                "rate_limit": {
                    "window_seconds": 60,
                    "max_requests_per_user": 20,
                    "max_requests_per_tenant": 200,
                },
            }
        }
        return JSONConfigProvider(data)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Basic validation to fail fast on common mistakes
    if not isinstance(data, dict):
        msg = "Config JSON root must be an object"
        raise TypeError(msg)
    default = data.get("default", {})
    if default is not None and not isinstance(default, dict):
        msg_default = "'default' must be an object"
        raise ValueError(msg_default)
    tenants = data.get("tenants", {})
    if tenants is not None and not isinstance(tenants, dict):
        msg_tenants = "'tenants' must be an object"
        raise ValueError(msg_tenants)

    return JSONConfigProvider(data)
