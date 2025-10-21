"""Session management implementation for flow processing."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.core.session import SessionManager
from app.flow_core.state import FlowContext

if TYPE_CHECKING:
    from app.core.state import ConversationStore

logger = logging.getLogger(__name__)


class RedisSessionManager(SessionManager):
    """Redis-based implementation of session management."""

    def __init__(self, store: ConversationStore):
        self._store = store

    def create_session(self, user_id: str, flow_id: str) -> str:
        """Create a new flow session."""
        session_id = f"flow:{user_id}:{flow_id}"

        # Update current reply ID for interruption handling
        from uuid import uuid4

        reply_id = str(uuid4())
        from app.core.redis_keys import redis_keys

        current_reply_key = redis_keys.current_reply_key(user_id)
        key_suffix = current_reply_key.replace("chatai:state:system:", "")
        self._store.save(
            "system", key_suffix, {"reply_id": reply_id, "timestamp": int(time.time())}
        )

        logger.debug("Created session %s with reply ID %s", session_id, reply_id)
        return session_id

    def load_context(self, session_id: str) -> FlowContext | None:
        """Load existing flow context."""
        # Extract user_id from session_id for compatibility
        parts = session_id.split(":")
        if len(parts) >= 2:
            user_id = parts[1]
            existing_context_data = self._store.load(user_id, session_id)

            if existing_context_data and isinstance(existing_context_data, dict):
                try:
                    context = FlowContext.from_dict(existing_context_data)
                    logger.debug("Loaded existing flow context for session %s", session_id)
                    return context
                except Exception as e:
                    logger.warning("Failed to deserialize flow context, creating new: %s", e)

        return None

    def get_context(self, session_id: str) -> FlowContext | None:
        """Get flow context for a session (alias for load_context)."""
        return self.load_context(session_id)

    def save_context(self, session_id: str, context: FlowContext) -> None:
        """Save flow context."""
        # Extract user_id from session_id for compatibility
        parts = session_id.split(":")
        if len(parts) >= 2:
            user_id = parts[1]
            try:
                self._store.save(user_id, session_id, context.to_dict())
                logger.debug("Saved flow context for session %s", session_id)
            except Exception as e:
                logger.error("Failed to save flow context: %s", e)

    def clear_context(self, session_id: str) -> None:
        """Clear flow context."""
        # Extract user_id from session_id for compatibility
        parts = session_id.split(":")
        if len(parts) >= 2:
            user_id = parts[1]
            try:
                self._store.save(user_id, session_id, {})
                logger.debug("Cleared flow context for session %s", session_id)
            except Exception as e:
                logger.warning("Failed to clear flow context: %s", e)
