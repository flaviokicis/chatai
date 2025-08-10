from __future__ import annotations

from app.core.messages import InboundMessage


def test_questionnaire_agent_persists_state_and_completes(make_agent, store) -> None:
    agent = make_agent([{"updates": {"a": "va"}}, {"updates": {"b": "vb"}}])

    # First turn: A answered, B should be asked next
    response_first = agent.handle(
        InboundMessage(user_id="u", text="hi", channel="test", metadata={})
    )
    assert response_first.outbound is not None
    assert response_first.outbound.text == "Ask B?"

    state_after_first = store.load("u", agent.agent_type)
    assert isinstance(state_after_first, dict)
    assert state_after_first.get("answers", {}).get("a") == "va"
    assert state_after_first.get("pending_field") == "b"

    # Second turn: B answered, should escalate to human as checklist complete
    response_second = agent.handle(
        InboundMessage(user_id="u", text="more", channel="test", metadata={})
    )
    assert response_second.outbound is not None
    assert "Transferring" in response_second.outbound.text

    state_after_second = store.load("u", agent.agent_type)
    assert isinstance(state_after_second, dict)
    assert state_after_second.get("answers", {}).get("b") == "vb"
    assert state_after_second.get("pending_field") is None


def test_questionnaire_agent_llm_requested_escalation(make_agent) -> None:
    agent = make_agent([{"__tool_name__": "EscalateToHuman", "reason": "ambiguous", "summary": {}}])
    result = agent.handle(InboundMessage(user_id="u", text="?", channel="test", metadata={}))
    assert result.outbound is not None
    assert "Transferring" in result.outbound.text
