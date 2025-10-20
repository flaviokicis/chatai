import asyncio
import json
import time

import pytest


class FakeRedis:
    """Complete fake Redis implementation for testing ProcessingCancellationManager."""

    def __init__(self):
        self._lists = {}
        self._strings = {}
        self._counters = {}

    def lrange(self, key, start, end):
        items = self._lists.get(key, [])
        if end == -1:
            return items[start:]
        return items[start : end + 1]

    def rpush(self, key, value):
        self._lists.setdefault(key, []).append(value)

    def llen(self, key):
        return len(self._lists.get(key, []))

    def expire(self, key, ttl):
        pass

    def get(self, key):
        return self._strings.get(key)
    
    def set(self, key, value):
        self._strings[key] = value

    def setex(self, key, ttl, value):
        self._strings[key] = value
    
    def incr(self, key):
        current = self._counters.get(key, 0)
        self._counters[key] = current + 1
        return self._counters[key]

    def delete(self, *keys):
        for key in keys:
            self._lists.pop(key, None)
            self._strings.pop(key, None)
            self._counters.pop(key, None)

    def pipeline(self):
        return FakeRedisPipeline(self)


class FakeRedisPipeline:
    """Fake Redis pipeline for atomic operations."""

    def __init__(self, redis):
        self._redis = redis
        self._commands = []

    def lrange(self, key, start, end):
        self._commands.append(("lrange", key, start, end))
        return self
    
    def rpush(self, key, value):
        self._commands.append(("rpush", key, value))
        return self
    
    def set(self, key, value):
        self._commands.append(("set", key, value))
        return self
    
    def setex(self, key, ttl, value):
        self._commands.append(("setex", key, ttl, value))
        return self
    
    def expire(self, key, ttl):
        self._commands.append(("expire", key, ttl))
        return self

    def delete(self, *keys):
        self._commands.append(("delete", keys))
        return self

    def execute(self):
        results = []
        for cmd in self._commands:
            if cmd[0] == "lrange":
                results.append(self._redis.lrange(cmd[1], cmd[2], cmd[3]))
            elif cmd[0] == "rpush":
                self._redis.rpush(cmd[1], cmd[2])
                results.append(len(self._redis._lists.get(cmd[1], [])))
            elif cmd[0] == "set":
                self._redis.set(cmd[1], cmd[2])
                results.append("OK")
            elif cmd[0] == "setex":
                self._redis.setex(cmd[1], cmd[2], cmd[3])
                results.append("OK")
            elif cmd[0] == "expire":
                self._redis.expire(cmd[1], cmd[2])
                results.append(1)
            elif cmd[0] == "delete":
                self._redis.delete(*cmd[1])
                results.append(len(cmd[1]))
        return results


class FakeStore:
    """Fake store with FakeRedis."""

    def __init__(self):
        self._r = FakeRedis()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_for_inactivity_exits_when_newer_message_arrives():
    from app.services.processing_cancellation_manager import ProcessingCancellationManager

    store = FakeStore()
    pcm = ProcessingCancellationManager(store=store)

    session_id = "flow:user:flowid"
    first_id = pcm.add_message_to_buffer(session_id, "hello")

    async def trigger_newer():
        await asyncio.sleep(0.05)
        pcm.add_message_to_buffer(session_id, "world")

    task = asyncio.create_task(trigger_newer())
    result = await pcm.wait_for_inactivity(
        session_id, first_id, inactivity_ms=500, check_interval_ms=50
    )
    await task

    assert result == "exit"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_for_inactivity_aggregates_multiple_messages():
    from app.services.processing_cancellation_manager import ProcessingCancellationManager

    store = FakeStore()
    pcm = ProcessingCancellationManager(store=store)

    session_id = "flow:user:flowid"
    mid1 = pcm.add_message_to_buffer(session_id, "one")
    mid2 = pcm.add_message_to_buffer(session_id, "two")

    start = time.time()
    result = await pcm.wait_for_inactivity(
        session_id, mid2, inactivity_ms=120, check_interval_ms=20
    )
    elapsed = (time.time() - start) * 1000

    assert result == "process_aggregated"
    assert elapsed >= 100


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_for_inactivity_single_message():
    from app.services.processing_cancellation_manager import ProcessingCancellationManager

    store = FakeStore()
    pcm = ProcessingCancellationManager(store=store)

    session_id = "flow:user:flowid"
    mid1 = pcm.add_message_to_buffer(session_id, "only")

    result = await pcm.wait_for_inactivity(
        session_id, mid1, inactivity_ms=80, check_interval_ms=20
    )
    assert result == "process_single"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_and_clear_messages_aggregates_with_timestamps():
    from app.services.processing_cancellation_manager import ProcessingCancellationManager

    store = FakeStore()
    pcm = ProcessingCancellationManager(store=store)

    session_id = "flow:user:flowid"
    pcm.add_message_to_buffer(session_id, "first")
    await asyncio.sleep(0.05)
    pcm.add_message_to_buffer(session_id, "second")
    await asyncio.sleep(0.05)
    pcm.add_message_to_buffer(session_id, "third")

    aggregated = pcm.get_and_clear_messages(session_id)

    assert aggregated is not None
    assert "first" in aggregated
    assert "second" in aggregated
    assert "third" in aggregated

    count = pcm.get_message_count(session_id)
    assert count == 0


