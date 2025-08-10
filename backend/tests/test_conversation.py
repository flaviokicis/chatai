import pytest


@pytest.mark.skip(reason="Legacy ConversationManager removed in refactor")
def test_legacy_conversation_removed() -> None:
    assert True
