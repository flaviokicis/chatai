"""Test suite for flow chat clear functionality."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Flow, FlowChatRole, FlowChatSession
from app.db.repository import (
    clear_flow_chat_messages,
    create_flow_chat_message,
    list_flow_chat_messages,
)


def test_clear_chat_messages_creates_session_record(db_session: Session):
    """Test that clearing chat creates a session record with cleared_at timestamp."""
    flow_id = uuid4()

    # Create a flow record (simplified for test)
    flow = Flow(
        id=flow_id,
        tenant_id=uuid4(),
        channel_instance_id=uuid4(),
        name="Test Flow",
        flow_id="test_flow",
        definition={"nodes": [], "edges": []},
    )
    db_session.add(flow)
    db_session.commit()

    # Add some chat messages
    msg1 = create_flow_chat_message(
        db_session,
        flow_id=flow_id,
        role=FlowChatRole.user,
        content="Hello"
    )
    msg2 = create_flow_chat_message(
        db_session,
        flow_id=flow_id,
        role=FlowChatRole.assistant,
        content="Hi there!"
    )
    db_session.commit()

    # Verify messages exist
    messages = list_flow_chat_messages(db_session, flow_id)
    assert len(messages) == 2

    # Clear the chat
    clear_time_before = datetime.now(UTC)
    clear_flow_chat_messages(db_session, flow_id)
    clear_time_after = datetime.now(UTC)
    db_session.commit()

    # Verify session record was created
    session_record = db_session.query(FlowChatSession).filter_by(flow_id=flow_id).first()
    assert session_record is not None
    assert session_record.cleared_at is not None

    # Handle potential timezone conversion from SQLite
    cleared_at = session_record.cleared_at
    if cleared_at.tzinfo is None:
        # If timezone-naive, assume UTC
        cleared_at = cleared_at.replace(tzinfo=UTC)

    assert clear_time_before <= cleared_at <= clear_time_after

    # Verify messages are now filtered out
    messages_after_clear = list_flow_chat_messages(db_session, flow_id)
    assert len(messages_after_clear) == 0


def test_messages_after_clear_are_visible(db_session: Session):
    """Test that messages sent after clearing are visible."""
    flow_id = uuid4()

    # Create a flow record
    flow = Flow(
        id=flow_id,
        tenant_id=uuid4(),
        channel_instance_id=uuid4(),
        name="Test Flow",
        flow_id="test_flow",
        definition={"nodes": [], "edges": []},
    )
    db_session.add(flow)
    db_session.commit()

    # Add messages, clear, then add more messages
    create_flow_chat_message(db_session, flow_id=flow_id, role=FlowChatRole.user, content="Before clear")
    db_session.commit()

    # Clear the chat
    clear_flow_chat_messages(db_session, flow_id)
    db_session.commit()

    # Add a delay to ensure different timestamps (1+ second for SQLite precision)
    import time
    time.sleep(1.1)

    # Add messages after clear
    create_flow_chat_message(db_session, flow_id=flow_id, role=FlowChatRole.user, content="After clear")
    db_session.commit()

    # Verify only post-clear messages are visible
    messages = list_flow_chat_messages(db_session, flow_id)
    assert len(messages) == 1
    assert messages[0].content == "After clear"


def test_clear_chat_api_endpoint():
    """Test the clear chat API endpoint using mocks."""
    from unittest.mock import patch

    from app.main import app

    flow_id = uuid4()

    # Mock at the API level where it's imported
    with patch("app.api.flow_chat.clear_flow_chat_messages") as mock_clear:
        with TestClient(app) as client:
            # Call the clear endpoint
            response = client.post(f"/flows/{flow_id}/chat/clear")

            # Verify success response
            assert response.status_code == 200
            assert response.json() == {"message": "Chat cleared successfully"}

            # Verify the repository function was called
            mock_clear.assert_called_once()
            # The first argument should be a session, second should be the flow_id
            args, kwargs = mock_clear.call_args
            assert args[1] == flow_id  # flow_id is the second argument

