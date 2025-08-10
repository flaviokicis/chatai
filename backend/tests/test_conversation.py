from typing import Any, Protocol

from app.conversation import ConversationManager


class SupportsToolsLLM(Protocol):
    def bind_tools(self, tools: list[object]) -> "SupportsToolsLLM": ...

    def invoke(self, _prompt: str) -> object: ...


class DummyLLM:
    def __init__(self, updates: list[dict[str, Any]]) -> None:
        self._updates = updates
        self._idx = 0

    def bind_tools(self, tools: list[object]) -> "DummyLLM":
        return self

    def invoke(self, _prompt: str) -> object:
        if self._idx < len(self._updates):
            args: dict[str, Any] = self._updates[self._idx]
            self._idx += 1
        else:
            args = {}
        return type(
            "Msg",
            (),
            {
                "tool_calls": [{"name": "UpdateChecklist", "args": args}] if args else [],
            },
        )()


def test_conversation_flow_minimal() -> None:
    updates: list[dict[str, Any]] = [
        {"intention": "buy led lights"},
        {"is_sports_court_led": True, "sport": "tennis"},
        {"covered_from_rain": False},
        {"dimensions": "28 x 15 m"},
    ]
    cm = ConversationManager()
    user = "+10000000000"
    llm: SupportsToolsLLM = DummyLLM(updates)

    assert cm.handle(user, "hi", llm) == "Is your intention to buy LED lights for a sports court?"
    assert (
        cm.handle(user, "yes, led lights for a tennis court", llm)
        == "Is the court covered from rain or is it in the open?"
    )
    assert (
        cm.handle(user, "it's outdoor", llm)
        == "What are the dimensions of the court? (e.g., 28 x 15 m)"
    )
    assert cm.handle(user, "it's 28 x 15 m", llm) == "All good, transfering to human"


def test_yes_no_affirmations() -> None:
    # Only the intention is extracted initially; then we answer yes to sports court question.
    updates: list[dict[str, Any]] = [
        {"intention": "buy leds"},  # after "hello", we simulate intention from next message
        {"is_sports_court_led": True},  # LLM interprets "yes" based on pending_field
    ]
    cm = ConversationManager()
    user = "+12223334444"
    llm: SupportsToolsLLM = DummyLLM(updates)

    # First message should ask intention (since state is empty)
    res1 = cm.handle(user, "hello", llm)
    assert res1 in {
        "What is your intention?",
        "Is your intention to buy LED lights for a sports court?",
    }
    # Provide intention; next question should be sports-court or jump to sport if LLM already confirmed
    res2 = cm.handle(user, "buy leds", llm)
    if res2 == "Is your intention to buy LED lights for a sports court?":
        assert cm.handle(user, "yes", llm) == "Which sport is the court for?"
    else:
        assert res2 == "Which sport is the court for?"
