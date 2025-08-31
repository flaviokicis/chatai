from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.agents.base import BaseAgentDeps, FlowAgent
from app.core.llm import LLMClient
from app.core.state import InMemoryStore
from app.flow_core.builders import build_flow_from_questions
from app.flow_core.compiler import compile_flow
from app.main import app
from app.services.human_handoff import LoggingHandoff


class SeqLLM(LLMClient):
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
def compiled_flow():
    flow = build_flow_from_questions(
        [
            {"key": "a", "prompt": "Ask A?", "priority": 10},
            {"key": "b", "prompt": "Ask B?", "priority": 20, "dependencies": ["a"]},
        ],
        flow_id="test",
    )
    return compile_flow(flow)


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def handoff() -> LoggingHandoff:
    return LoggingHandoff()


@pytest.fixture
def make_agent(store: InMemoryStore, handoff: LoggingHandoff, compiled_flow):
    def _make(results: list[dict[str, Any]]):
        llm = SeqLLM(results)
        deps = BaseAgentDeps(store=store, llm=llm, handoff=handoff)
        return FlowAgent("u", deps, compiled_flow=compiled_flow)

    return _make


@pytest.fixture(scope="function")
def db_session():
    """Create a test database session using in-memory SQLite."""
    # Set up encryption key for EncryptedString fields
    if not os.environ.get("PII_ENCRYPTION_KEY"):
        from cryptography.fernet import Fernet
        os.environ["PII_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

    # Create SQLite engine
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False}
    )

    # Disable foreign key constraints for SQLite testing
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    # Create the specific tables we need for clear chat functionality tests
    from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, Text
    from sqlalchemy.dialects.sqlite import JSON

    test_metadata = MetaData()

    # Create flows table (replace JSONB definition with JSON)
    from sqlalchemy.sql import func

    # Include all columns that the Flow model expects (including TimestampMixin)
    flows_table = Table(
        "flows", test_metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String),
        Column("channel_instance_id", String),
        Column("name", String),
        Column("flow_id", String),
        Column("definition", JSON),  # JSONB -> JSON
        Column("is_active", Boolean, default=True),
        Column("version", Integer, default=1),
        Column("created_at", DateTime, nullable=False, server_default=func.now()),
        Column("updated_at", DateTime, nullable=False, server_default=func.now()),
        Column("deleted_at", DateTime, nullable=True),  # From TimestampMixin
    )

    # Create flow_chat_messages table
    # Include all columns that FlowChatMessage model expects
    flow_chat_messages_table = Table(
        "flow_chat_messages", test_metadata,
        Column("id", String, primary_key=True),
        Column("flow_id", String),
        Column("role", String),
        Column("content", Text),
        Column("created_at", DateTime, nullable=False, server_default=func.now()),
        Column("updated_at", DateTime, nullable=False, server_default=func.now()),
        Column("deleted_at", DateTime, nullable=True),  # From TimestampMixin
    )

    # Create flow_chat_sessions table
    # Include all columns that FlowChatSession model expects
    flow_chat_sessions_table = Table(
        "flow_chat_sessions", test_metadata,
        Column("id", String, primary_key=True),
        Column("flow_id", String),
        Column("cleared_at", DateTime, nullable=True),
        Column("created_at", DateTime, nullable=False, server_default=func.now()),
        Column("updated_at", DateTime, nullable=False, server_default=func.now()),
        Column("deleted_at", DateTime, nullable=True),  # From TimestampMixin
    )

    # Create tables
    test_metadata.create_all(bind=engine)

    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client():
    """Create a test client for FastAPI."""
    return TestClient(app)



