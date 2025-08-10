from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Protocol

try:
    from langchain_community.chat_message_histories import RedisChatMessageHistory
except Exception:  # pragma: no cover - optional import
    RedisChatMessageHistory = None  # type: ignore[assignment,unused-ignore]
try:
    import redis
except Exception:  # pragma: no cover - optional import
    redis = None  # type: ignore[assignment,unused-ignore]

if TYPE_CHECKING:
    from .agent_base import AgentState


class ConversationStore(Protocol):
    def load(self, user_id: str, agent_type: str) -> AgentState | None: ...

    def save(self, user_id: str, agent_type: str, state: AgentState) -> None: ...

    def append_event(self, user_id: str, event: dict) -> None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._states: dict[tuple[str, str], AgentState] = {}
        self._events: dict[str, list[dict]] = {}

    def load(self, user_id: str, agent_type: str) -> AgentState | None:
        return self._states.get((user_id, agent_type))

    def save(self, user_id: str, agent_type: str, state: AgentState) -> None:
        self._states[(user_id, agent_type)] = state

    def append_event(self, user_id: str, event: dict) -> None:
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

    def _state_key(self, user_id: str, agent_type: str) -> str:
        return f"{self._ns}:state:{user_id}:{agent_type}"

    def _events_key(self, user_id: str) -> str:
        return f"{self._ns}:events:{user_id}"

    def load(self, user_id: str, agent_type: str) -> AgentState | None:  # type: ignore[name-defined]
        raw = self._r.get(self._state_key(user_id, agent_type))
        if not raw:
            return None
        try:
            body = raw.decode("utf-8") if isinstance(raw, bytes | bytearray) else raw
            data = json.loads(body)
        except Exception:
            return None
        return data  # type: ignore[return-value]

    def save(self, user_id: str, agent_type: str, state: AgentState) -> None:  # type: ignore[name-defined]
        # state may be a dict-like as our concrete agents store dicts
        if isinstance(state, dict):
            payload: Any = state
        elif hasattr(state, "to_dict"):
            payload = state.to_dict()  # type: ignore[call-arg]
        else:
            payload = {}
        body = json.dumps(payload)
        key = self._state_key(user_id, agent_type)
        if self._state_ttl:
            self._r.setex(key, self._state_ttl, body)
        else:
            self._r.set(key, body)

    def append_event(self, user_id: str, event: dict) -> None:
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
        return RedisChatMessageHistory(
            session_id=session_id,
            client=self._r,
            key_prefix=f"{self._ns}:history:",
        )
