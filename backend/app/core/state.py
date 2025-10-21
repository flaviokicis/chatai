from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Protocol

# Local import to avoid circular dependencies at module import time
from app.core.redis_keys import RedisKeyBuilder

logger = logging.getLogger(__name__)

try:
    from langchain_community.chat_message_histories import (
        RedisChatMessageHistory,
    )
except Exception:  # pragma: no cover - optional import
    RedisChatMessageHistory = None
try:
    import redis
except Exception:  # pragma: no cover - optional import
    redis = None

if TYPE_CHECKING:
    from .agent_base import AgentState

from app.core.types import EventDict


class ConversationStore(Protocol):
    _r: Any
    
    def load(self, user_id: str, agent_type: str) -> AgentState | None: ...

    def save(self, user_id: str, agent_type: str, state: AgentState) -> None: ...

    def append_event(self, user_id: str, event: EventDict) -> None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._states: dict[tuple[str, str], AgentState] = {}
        self._events: dict[str, list[EventDict]] = {}

    def load(self, user_id: str, agent_type: str) -> AgentState | None:
        return self._states.get((user_id, agent_type))

    def save(self, user_id: str, agent_type: str, state: AgentState) -> None:
        self._states[(user_id, agent_type)] = state

    def append_event(self, user_id: str, event: EventDict) -> None:
        """Append typed event to the event list."""
        # Validate event has required fields
        if "timestamp" not in event:
            import time

            event["timestamp"] = time.time()
        if "type" not in event:
            raise ValueError("Event must have a 'type' field")
        self._events.setdefault(user_id, []).append(event)


class RedisStore:
    """Conversation store backed by Redis.

    Stores per-(user_id, agent_type) state as JSON and appends events to a list.
    Optionally exposes a LangChain RedisChatMessageHistory for message transcripts.
    """

    def __init__(
        self,
        redis_url: str,
        *,
        namespace: str = "chatai",
        state_ttl: timedelta | None = timedelta(days=30),
        events_ttl: timedelta | None = timedelta(days=30),
    ) -> None:
        if redis is None:  # pragma: no cover - import guard
            msg = "redis-py is not installed. Please add 'redis' to dependencies."
            raise RuntimeError(msg)
        self._r = redis.from_url(redis_url)
        self._ns = namespace.rstrip(":")
        self._state_ttl = int(state_ttl.total_seconds()) if state_ttl else None
        self._events_ttl = int(events_ttl.total_seconds()) if events_ttl else None

    @property
    def redis_client(self) -> object:
        """Public access to Redis client for advanced operations."""
        return self._r

    def _state_key(self, user_id: str, agent_type: str) -> str:
        # Use centralized key builder for consistency with our namespace
        key_builder = RedisKeyBuilder(namespace=self._ns)
        return key_builder.conversation_state_key(user_id, agent_type)

    def _events_key(self, user_id: str) -> str:
        return f"{self._ns}:events:{user_id}"  # Events use simple pattern

    def load(self, user_id: str, agent_type: str) -> AgentState | None:
        """Load agent state with proper typing and validation."""
        raw = self._r.get(self._state_key(user_id, agent_type))
        if not raw:
            return None
        try:
            body = raw.decode("utf-8") if isinstance(raw, bytes | bytearray) else raw
            data = json.loads(body)
        except Exception as e:
            logger.warning(f"Failed to decode state for {user_id}/{agent_type}: {e}")
            return None

        # For flow agents, try to convert to FlowContext which implements AgentState
        if agent_type == "flow_agent" and isinstance(data, dict):
            # Import here to avoid circular dependency
            from app.flow_core.state import FlowContext

            try:
                # FlowContext has from_dict method
                if hasattr(FlowContext, "from_dict"):
                    return FlowContext.from_dict(data)
                # Otherwise return the dict - it should implement the protocol
                # This is a temporary fallback until all agents properly implement AgentState
                return data  # type: ignore[return-value]
            except Exception as e:
                logger.error(f"Failed to reconstruct FlowContext: {e}")
                return None

        # For other agent types, return the data if it implements the protocol
        # In practice, agents return dicts that follow the AgentState protocol
        if isinstance(data, dict):
            return data  # type: ignore[return-value]

        return None

    def save(self, user_id: str, agent_type: str, state: AgentState) -> None:
        # state may be a dict-like as our concrete agents store dicts
        if isinstance(state, dict):
            payload: Any = state
        elif hasattr(state, "to_dict"):
            payload = state.to_dict()
        else:
            payload = {}
        body = json.dumps(payload)
        key = self._state_key(user_id, agent_type)
        if self._state_ttl:
            self._r.setex(key, self._state_ttl, body)
        else:
            self._r.set(key, body)

    def append_event(self, user_id: str, event: EventDict) -> None:
        """Append typed event with validation."""
        # Validate event has required fields
        if "timestamp" not in event:
            import time

            event["timestamp"] = time.time()
        if "type" not in event:
            raise ValueError("Event must have a 'type' field")

        key = self._events_key(user_id)
        try:
            self._r.rpush(key, json.dumps(event))
            if self._events_ttl:
                self._r.expire(key, self._events_ttl)
        except Exception:
            # best-effort logging store; ignore failures
            return

    def get_message_history(self, session_id: str) -> object:
        """Return a LangChain RedisChatMessageHistory for a session id.

        Requires langchain_community to be installed. If missing, raises RuntimeError.
        """
        if RedisChatMessageHistory is None:  # pragma: no cover - optional dependency
            msg = "langchain_community is not installed. Add 'langchain-community' to dependencies."
            raise RuntimeError(msg)

        # LangChain RedisChatMessageHistory signature changed across versions.
        # Try different parameter combinations based on the version

        # Try 1: Current versions use 'url' parameter (most common)
        try:
            # Get the Redis URL from the connection
            pool_kwargs = self._r.connection_pool.connection_kwargs
            host = pool_kwargs.get("host", "localhost")
            port = int(pool_kwargs.get("port", 6379))
            db = int(pool_kwargs.get("db", 0))
            password = pool_kwargs.get("password", "")

            # Build URL
            if password:
                url = f"redis://:{password}@{host}:{port}/{db}"
            else:
                url = f"redis://{host}:{port}/{db}"

            return RedisChatMessageHistory(
                session_id=session_id,
                url=url,  # current versions use url parameter
                key_prefix=f"{self._ns}:history:",
            )
        except (TypeError, KeyError) as e1:
            logger.debug("RedisChatMessageHistory with url failed: %s", e1)

        # Try 2: Some versions use 'redis_client'
        try:
            return RedisChatMessageHistory(
                session_id=session_id,
                redis_client=self._r,  # some versions use redis_client
                key_prefix=f"{self._ns}:history:",
            )
        except TypeError as e2:
            logger.debug("RedisChatMessageHistory with redis_client failed: %s", e2)

        # Try 3: Older versions use host/port/db parameters
        try:
            pool_kwargs = self._r.connection_pool.connection_kwargs
            return RedisChatMessageHistory(
                session_id=session_id,
                redis_host=pool_kwargs.get("host", "localhost"),  # Note: redis_host not just host
                redis_port=int(pool_kwargs.get("port", 6379)),
                redis_db=int(pool_kwargs.get("db", 0)),
                redis_password=pool_kwargs.get("password"),
                key_prefix=f"{self._ns}:history:",
            )
        except (TypeError, KeyError) as e3:
            logger.debug("RedisChatMessageHistory with redis_host/port/db failed: %s", e3)

        # Try 4: Even older versions might use different param names
        try:
            pool_kwargs = self._r.connection_pool.connection_kwargs
            return RedisChatMessageHistory(
                session_id=session_id,
                host=pool_kwargs.get("host", "localhost"),
                port=int(pool_kwargs.get("port", 6379)),
                db=int(pool_kwargs.get("db", 0)),
                key_prefix=f"{self._ns}:history:",
            )
        except (TypeError, KeyError) as e4:
            logger.debug("RedisChatMessageHistory with host/port/db failed: %s", e4)

        # If all attempts fail, raise an informative error
        msg = (
            "Failed to initialize RedisChatMessageHistory. "
            "This might be due to a version mismatch in langchain-community. "
            "Please check your langchain-community version."
        )
        raise RuntimeError(msg)

    def set_escalation_timestamp(self, user_id: str, agent_type: str) -> None:
        """Mark when escalation occurred for delayed context clearing.

        Args:
            user_id: User identifier
            agent_type: Agent type that escalated
        """
        import time

        key = f"{self._ns}:escalation:{user_id}:{agent_type}"
        self._r.setex(key, 86400, str(time.time()))

    def get_escalation_timestamp(self, user_id: str, agent_type: str) -> float | None:
        """Get escalation timestamp if exists.

        Args:
            user_id: User identifier
            agent_type: Agent type

        Returns:
            Timestamp of escalation or None if not escalated
        """
        key = f"{self._ns}:escalation:{user_id}:{agent_type}"
        value = self._r.get(key)
        if value:
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return None

    def clear_escalation_timestamp(self, user_id: str, agent_type: str) -> None:
        """Clear escalation timestamp.

        Args:
            user_id: User identifier
            agent_type: Agent type
        """
        key = f"{self._ns}:escalation:{user_id}:{agent_type}"
        self._r.delete(key)

    def should_clear_context_after_escalation(
        self, user_id: str, agent_type: str, grace_period_seconds: int
    ) -> bool:
        """Check if enough time has passed since escalation to clear context.

        Args:
            user_id: User identifier
            agent_type: Agent type
            grace_period_seconds: How long to wait before clearing

        Returns:
            True if grace period has passed and context should be cleared
        """
        import time

        escalation_time = self.get_escalation_timestamp(user_id, agent_type)
        if escalation_time is None:
            return False

        elapsed = time.time() - escalation_time
        return elapsed >= grace_period_seconds

    def clear_chat_history(self, user_id: str, agent_type: str | None = None) -> int:
        """Clear chat history for a user and optionally specific agent type.

        Args:
            user_id: User identifier (e.g., "whatsapp:5522988544370")
            agent_type: Optional agent type to clear specific flow history

        Returns:
            Number of keys deleted
        """
        deleted_keys = 0

        try:
            # Extract phone number for broader matching
            phone_number = user_id.replace("whatsapp:", "").replace("+", "")

            if agent_type and agent_type.startswith("flow."):
                # Clear specific flow history
                flow_id = agent_type
                patterns = [
                    f"{self._ns}:history:*{phone_number}*{flow_id}*",
                    f"{self._ns}:history:*{user_id}*{flow_id}*",
                ]
            else:
                # Clear all chat history for user
                patterns = [
                    f"{self._ns}:history:*{phone_number}*",
                    f"{self._ns}:history:*{user_id}*",
                ]

            # Delete keys using patterns
            for pattern in patterns:
                keys = self._r.keys(pattern)
                if keys:
                    deleted_count = self._r.delete(*keys)
                    deleted_keys += deleted_count

        except Exception as e:
            # Best-effort clearing; don't fail the handoff if clearing fails
            logger.warning("Failed to clear chat history for user %s: %s", user_id, e)

        return deleted_keys
