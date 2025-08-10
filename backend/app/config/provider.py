from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class LLMInstanceConfig:
    provider: str | None = None
    model: str | None = None


@dataclass(slots=True)
class AgentInstanceConfig:
    instance_id: str
    agent_type: str
    params: dict[str, Any]
    handoff: dict[str, Any]
    llm: LLMInstanceConfig | None = None


@dataclass(slots=True)
class ChannelAgentConfig:
    channel_type: str
    channel_id: str
    enabled_agents: list[str]
    agent_instances: list[AgentInstanceConfig]
    default_instance_id: str | None


@dataclass(slots=True)
class TenantAgentConfig:
    enabled_agents: list[str]
    channels: list[ChannelAgentConfig]


class ConfigProvider(Protocol):
    def get_tenant_config(self, tenant_id: str) -> TenantAgentConfig: ...
    def get_enabled_agents(
        self, tenant_id: str, channel_type: str | None, channel_id: str | None
    ) -> list[str]: ...
    def get_channel_config(
        self, tenant_id: str, channel_type: str, channel_id: str
    ) -> ChannelAgentConfig | None: ...


class JSONConfigProvider:
    def __init__(self, data: dict[str, object]) -> None:
        self._data = data

    def _get_raw_tenant(self, tenant_id: str) -> dict[str, Any]:
        tenants = self._data.get("tenants", {})
        raw = tenants.get(tenant_id) if isinstance(tenants, dict) else None
        if not isinstance(raw, dict):
            raw = self._data.get("default", {}) if isinstance(self._data, dict) else {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _parse_enabled_agents(raw: dict[str, Any]) -> list[str]:
        enabled = (
            raw.get("enabled_agents", ["sales_qualifier"])
            if isinstance(raw, dict)
            else ["sales_qualifier"]
        )
        if not isinstance(enabled, list):
            return ["sales_qualifier"]
        return [str(a) for a in enabled]

    @staticmethod
    def _parse_instances(instances_raw: object) -> list[AgentInstanceConfig]:
        instances: list[AgentInstanceConfig] = []
        if isinstance(instances_raw, list):
            for inst in instances_raw:
                if not isinstance(inst, dict):
                    continue
                instance_id = str(inst.get("instance_id", "")).strip()
                agent_type = str(inst.get("agent_type", "")).strip()
                if not instance_id or not agent_type:
                    continue
                params = inst.get("params", {})
                handoff = inst.get("handoff", {})
                llm_raw = inst.get("llm", {})
                if not isinstance(params, dict):
                    params = {}
                if not isinstance(handoff, dict):
                    handoff = {}
                llm: LLMInstanceConfig | None = None
                if isinstance(llm_raw, dict):
                    provider_raw = llm_raw.get("provider")
                    model_raw = llm_raw.get("model")
                    provider = str(provider_raw).strip() if isinstance(provider_raw, str) else None
                    model = str(model_raw).strip() if isinstance(model_raw, str) else None
                    llm = LLMInstanceConfig(provider=provider or None, model=model or None)
                instances.append(
                    AgentInstanceConfig(
                        instance_id=instance_id,
                        agent_type=agent_type,
                        params={str(k): v for k, v in params.items()},
                        handoff={str(k): v for k, v in handoff.items()},
                        llm=llm,
                    )
                )
        return instances

    @classmethod
    def _parse_channels(cls, channels_raw: object) -> list[ChannelAgentConfig]:
        channels: list[ChannelAgentConfig] = []
        if isinstance(channels_raw, list):
            for item in channels_raw:
                if not isinstance(item, dict):
                    continue
                ctype = str(item.get("channel_type", "")).strip()
                cid = str(item.get("channel_id", "")).strip()
                if not ctype or not cid:
                    continue
                c_agents = item.get("enabled_agents", [])
                if not isinstance(c_agents, list):
                    c_agents = []
                instances = cls._parse_instances(item.get("agent_instances", []))
                default_iid_raw = item.get("default_instance_id")
                default_iid = (
                    str(default_iid_raw).strip() if isinstance(default_iid_raw, str) else None
                )
                channels.append(
                    ChannelAgentConfig(
                        channel_type=ctype,
                        channel_id=cid,
                        enabled_agents=[str(a) for a in c_agents],
                        agent_instances=instances,
                        default_instance_id=default_iid,
                    )
                )
        return channels

    def get_tenant_config(self, tenant_id: str) -> TenantAgentConfig:  # type: ignore[override]
        raw = self._get_raw_tenant(tenant_id)
        enabled_agents = self._parse_enabled_agents(raw)
        channels = self._parse_channels(raw.get("channels", []))
        return TenantAgentConfig(enabled_agents=enabled_agents, channels=channels)

    def get_enabled_agents(
        self, tenant_id: str, channel_type: str | None, channel_id: str | None
    ) -> list[str]:  # type: ignore[override]
        cfg = self.get_tenant_config(tenant_id)
        if channel_type and channel_id:
            for ch in cfg.channels:
                if ch.channel_type == channel_type and ch.channel_id == channel_id:
                    return ch.enabled_agents or cfg.enabled_agents
        return cfg.enabled_agents

    def get_channel_config(
        self, tenant_id: str, channel_type: str, channel_id: str
    ) -> ChannelAgentConfig | None:  # type: ignore[override]
        cfg = self.get_tenant_config(tenant_id)
        for ch in cfg.channels:
            if ch.channel_type == channel_type and ch.channel_id == channel_id:
                return ch
        return None
