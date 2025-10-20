import asyncio
import time
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from app.agents.base import BaseAgent, BaseAgentDeps
from app.core.messages import AgentResult, InboundMessage, OutboundMessage
from app.flow_core.constants import ESCALATION_CONTEXT_CLEAR_DELAY_SECONDS


class ConcreteTestAgent(BaseAgent):
    agent_type = "test_agent"
    
    def handle(self, message: InboundMessage) -> AgentResult:
        return AgentResult(
            outbound=OutboundMessage(text="Test response"),
            handoff=None,
            state_diff={},
        )


class MockRedisStore:
    def __init__(self):
        self._escalations = {}
        self._r = MagicMock()
        
    def set_escalation_timestamp(self, user_id: str, agent_type: str) -> None:
        key = f"{user_id}:{agent_type}"
        self._escalations[key] = time.time()
    
    def get_escalation_timestamp(self, user_id: str, agent_type: str) -> float | None:
        key = f"{user_id}:{agent_type}"
        return self._escalations.get(key)
    
    def clear_escalation_timestamp(self, user_id: str, agent_type: str) -> None:
        key = f"{user_id}:{agent_type}"
        self._escalations.pop(key, None)
    
    def should_clear_context_after_escalation(
        self, user_id: str, agent_type: str, grace_period_seconds: int
    ) -> bool:
        escalation_time = self.get_escalation_timestamp(user_id, agent_type)
        if escalation_time is None:
            return False
        elapsed = time.time() - escalation_time
        return elapsed >= grace_period_seconds
    
    def clear_chat_history(self, user_id: str, agent_type: str | None = None) -> int:
        return 5
    
    def load(self, user_id: str, agent_type: str) -> dict[str, Any] | None:
        return {"test": "data"}
    
    def save(self, user_id: str, agent_type: str, state: dict[str, Any]) -> None:
        pass


@pytest.mark.unit
def test_escalation_timestamp_is_set():
    store = MockRedisStore()
    llm = Mock()
    handoff = Mock()
    
    deps = BaseAgentDeps(store=store, llm=llm, handoff=handoff)
    agent = ConcreteTestAgent(user_id="test_user", deps=deps)
    
    result = agent._escalate("test_reason", {"test": "summary"})
    
    assert store.get_escalation_timestamp("test_user", agent.agent_type) is not None
    assert result.outbound.text == "Transferindo você para um atendente humano para mais assistência."
    assert result.handoff == {"reason": "test_reason", "summary": {"test": "summary"}}


@pytest.mark.unit
def test_context_not_cleared_immediately_after_escalation():
    store = MockRedisStore()
    llm = Mock()
    handoff = Mock()
    
    deps = BaseAgentDeps(store=store, llm=llm, handoff=handoff)
    agent = ConcreteTestAgent(user_id="test_user", deps=deps)
    
    agent._escalate("test_reason", {"test": "summary"})
    
    escalation_time = store.get_escalation_timestamp("test_user", agent.agent_type)
    assert escalation_time is not None
    
    elapsed = time.time() - escalation_time
    assert elapsed < 1.0


@pytest.mark.unit
def test_should_clear_after_grace_period():
    store = MockRedisStore()
    user_id = "test_user"
    agent_type = "test_agent"
    
    store.set_escalation_timestamp(user_id, agent_type)
    
    assert not store.should_clear_context_after_escalation(user_id, agent_type, 10)
    
    old_timestamp = time.time() - 15
    store._escalations[f"{user_id}:{agent_type}"] = old_timestamp
    
    assert store.should_clear_context_after_escalation(user_id, agent_type, 10)


@pytest.mark.unit
def test_should_not_clear_if_no_escalation():
    store = MockRedisStore()
    user_id = "test_user"
    agent_type = "test_agent"
    
    assert not store.should_clear_context_after_escalation(user_id, agent_type, 10)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delayed_clearing_background_task():
    store = MockRedisStore()
    llm = Mock()
    handoff = Mock()
    
    deps = BaseAgentDeps(store=store, llm=llm, handoff=handoff)
    agent = ConcreteTestAgent(user_id="test_user", deps=deps)
    
    short_delay = 0.1
    
    store.set_escalation_timestamp("test_user", agent.agent_type)
    assert store.get_escalation_timestamp("test_user", agent.agent_type) is not None
    
    await agent._clear_context_after_delay("test_user", agent.agent_type, short_delay)
    
    assert store.get_escalation_timestamp("test_user", agent.agent_type) is None


@pytest.mark.unit
def test_escalation_constant_is_set():
    assert ESCALATION_CONTEXT_CLEAR_DELAY_SECONDS == 300
    assert isinstance(ESCALATION_CONTEXT_CLEAR_DELAY_SECONDS, int)


@pytest.mark.unit  
def test_clear_escalation_timestamp():
    store = MockRedisStore()
    user_id = "test_user"
    agent_type = "test_agent"
    
    store.set_escalation_timestamp(user_id, agent_type)
    assert store.get_escalation_timestamp(user_id, agent_type) is not None
    
    store.clear_escalation_timestamp(user_id, agent_type)
    assert store.get_escalation_timestamp(user_id, agent_type) is None

