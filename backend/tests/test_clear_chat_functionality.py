"""Test suite for flow chat clear functionality."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Flow, FlowChatMessage, FlowChatRole, FlowChatSession
from app.db.repository import create_flow_chat_message, clear_flow_chat_messages, list_flow_chat_messages


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
    clear_time_before = datetime.now(timezone.utc)
    clear_flow_chat_messages(db_session, flow_id)
    clear_time_after = datetime.now(timezone.utc)
    db_session.commit()
    
    # Verify session record was created
    session_record = db_session.query(FlowChatSession).filter_by(flow_id=flow_id).first()
    assert session_record is not None
    assert session_record.cleared_at is not None
    assert clear_time_before <= session_record.cleared_at <= clear_time_after
    
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
    
    # Add messages after clear
    create_flow_chat_message(db_session, flow_id=flow_id, role=FlowChatRole.user, content="After clear")
    db_session.commit()
    
    # Verify only post-clear messages are visible
    messages = list_flow_chat_messages(db_session, flow_id)
    assert len(messages) == 1
    assert messages[0].content == "After clear"


def test_clear_chat_api_endpoint(client: TestClient, db_session: Session):
    """Test the clear chat API endpoint."""
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
    
    # Add some messages
    create_flow_chat_message(db_session, flow_id=flow_id, role=FlowChatRole.user, content="Test message")
    db_session.commit()
    
    # Call the clear endpoint
    response = client.post(f"/flows/{flow_id}/chat/clear")
    
    # Verify success response
    assert response.status_code == 200
    assert response.json() == {"message": "Chat cleared successfully"}
    
    # Verify messages are cleared
    messages = list_flow_chat_messages(db_session, flow_id)
    assert len(messages) == 0
