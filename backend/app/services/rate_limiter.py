from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

# Optional redis import for Redis backend
try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional import
    redis = None  # type: ignore[assignment,unused-ignore]


@dataclass(slots=True)
class RateLimitParams:
    window_seconds: int
    max_requests_per_user: int
    max_requests_per_tenant: int


class RateLimiterBackend(Protocol):
    def incr_with_ttl(self, key: str, ttl_seconds: int) -> int: ...


class InMemoryRateLimiterBackend:
    def __init__(self) -> None:
        # key -> (count, expires_at_epoch)
        self._store: dict[str, tuple[int, float]] = {}

    def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:  # type: ignore[override]
        now = time.time()
        count, exp = self._store.get(key, (0, 0.0))
        if exp <= now:
            # window expired or does not exist; reset
            count = 0
            exp = now + ttl_seconds
        count += 1
        self._store[key] = (count, exp)
        return count


class RedisRateLimiterBackend:
    def __init__(self, redis_url: str) -> None:
        if redis is None:  # type: no cover - import guard
            message = "redis-py is not installed"
            raise RuntimeError(message)
        self._r = redis.from_url(redis_url)

    def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:  # type: ignore[override]
        # Use INCR and set EXPIRE on first increment within the window
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        cnt, ttl = pipe.execute()
        # If key had no TTL (new key or persisted), set it now
        if ttl is None or ttl < 0:
            self._r.expire(key, ttl_seconds)
        return int(cnt)


class RateLimiter:
    def __init__(self, backend: RateLimiterBackend) -> None:
        self._backend = backend

    @staticmethod
    def _window_suffix(window_seconds: int) -> str:
        now = int(time.time())
        return str(now // window_seconds)

    def allow(self, tenant_id: str, user_id: str, params: RateLimitParams) -> tuple[bool, int, int]:
        """Increment counters and return allowance plus remaining budgets.

        Returns (allowed, remaining_user, remaining_tenant).
        """
        window = self._window_suffix(params.window_seconds)
        user_key = f"rl:u:{tenant_id}:{user_id}:{window}"
        tenant_key = f"rl:t:{tenant_id}:{window}"

        user_count = self._backend.incr_with_ttl(user_key, params.window_seconds)
        tenant_count = self._backend.incr_with_ttl(tenant_key, params.window_seconds)

        remaining_user = max(params.max_requests_per_user - user_count, 0)
        remaining_tenant = max(params.max_requests_per_tenant - tenant_count, 0)

        allowed = (
            user_count <= params.max_requests_per_user
            and tenant_count <= params.max_requests_per_tenant
        )
        return allowed, remaining_user, remaining_tenant
