"""Test the production-grade debouncing system.

This test validates that the debouncing system:
1. Properly resets timer on new messages
2. Aggregates messages correctly
3. Handles race conditions
4. Is idempotent (webhook retries)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.processing_cancellation_manager import ProcessingCancellationManager


def create_mock_redis_store() -> Any:
    """Create a mock Redis store for testing."""
    class FakeRedis:
        def __init__(self) -> None:
            self._data: dict[str, Any] = {}
            self._lists: dict[str, list[str]] = {}
            self._expiry: dict[str, float] = {}
        
        def pipeline(self) -> Any:
            return FakeRedisPipeline(self)
        
        def incr(self, key: str) -> int:
            val = self._data.get(key, "0")
            new_val = int(val) + 1
            self._data[key] = str(new_val)
            return new_val
        
        def get(self, key: str) -> str | None:
            return self._data.get(key)
        
        def set(self, key: str, value: str) -> None:
            self._data[key] = value
        
        def delete(self, *keys: str) -> None:
            for key in keys:
                self._data.pop(key, None)
                self._lists.pop(key, None)
        
        def rpush(self, key: str, value: str) -> None:
            if key not in self._lists:
                self._lists[key] = []
            self._lists[key].append(value)
        
        def lrange(self, key: str, start: int, end: int) -> list[str]:
            lst = self._lists.get(key, [])
            if end == -1:
                return lst[start:]
            return lst[start:end+1]
        
        def llen(self, key: str) -> int:
            return len(self._lists.get(key, []))
        
        def expire(self, key: str, seconds: int) -> None:
            import time
            self._expiry[key] = time.time() + seconds
        
        def setex(self, key: str, seconds: int, value: str) -> None:
            self.set(key, value)
            self.expire(key, seconds)
    
    class FakeRedisPipeline:
        def __init__(self, redis: FakeRedis):
            self.redis = redis
            self.commands: list[tuple[str, tuple, dict]] = []
        
        def incr(self, key: str) -> None:
            self.commands.append(("incr", (key,), {}))
        
        def lrange(self, key: str, start: int, end: int) -> None:
            self.commands.append(("lrange", (key, start, end), {}))
        
        def delete(self, *keys: str) -> None:
            self.commands.append(("delete", keys, {}))
        
        def rpush(self, key: str, value: str) -> None:
            self.commands.append(("rpush", (key, value), {}))
        
        def expire(self, key: str, seconds: int) -> None:
            self.commands.append(("expire", (key, seconds), {}))
        
        def set(self, key: str, value: str) -> None:
            self.commands.append(("set", (key, value), {}))
        
        def execute(self) -> list[Any]:
            results = []
            for cmd_name, args, kwargs in self.commands:
                method = getattr(self.redis, cmd_name)
                result = method(*args, **kwargs)
                results.append(result)
            self.commands = []
            return results
    
    mock_store = MagicMock()
    mock_store._r = FakeRedis()
    return mock_store


@pytest.mark.asyncio
async def test_basic_debouncing_resets_timer() -> None:
    """Test that new messages reset the inactivity timer."""
    store = create_mock_redis_store()
    manager = ProcessingCancellationManager(store=store)
    session_id = "test_session_1"
    
    msg_id_a = manager.add_message_to_buffer(session_id, "Message A")
    
    start_time = time.time()
    
    async def send_message_b_after_delay() -> str:
        await asyncio.sleep(0.5)
        msg_id_b = manager.add_message_to_buffer(session_id, "Message B")
        return msg_id_b
    
    task_b = asyncio.create_task(send_message_b_after_delay())
    
    result = await manager.wait_for_inactivity(
        session_id=session_id,
        since_message_id=msg_id_a,
        inactivity_ms=1000,
        check_interval_ms=100,
    )
    
    elapsed = time.time() - start_time
    
    assert result == "exit", "Message A should exit when newer message B arrives"
    assert elapsed < 1.0, "Message A should exit before inactivity period"
    
    msg_id_b = await task_b
    
    result_b = await manager.wait_for_inactivity(
        session_id=session_id,
        since_message_id=msg_id_b,
        inactivity_ms=1000,
        check_interval_ms=100,
    )
    
    assert result_b == "process_aggregated", "Message B should process after inactivity"
    
    aggregated = manager.get_and_clear_messages(session_id)
    assert aggregated is not None
    assert "Message A" in aggregated
    assert "Message B" in aggregated


@pytest.mark.asyncio
async def test_single_message_processing() -> None:
    """Test that single messages process correctly after inactivity."""
    store = create_mock_redis_store()
    manager = ProcessingCancellationManager(store=store)
    session_id = "test_session_2"
    
    msg_id = manager.add_message_to_buffer(session_id, "Single message")
    
    result = await manager.wait_for_inactivity(
        session_id=session_id,
        since_message_id=msg_id,
        inactivity_ms=500,
        check_interval_ms=100,
    )
    
    assert result == "process_single", "Single message should result in process_single"
    
    aggregated = manager.get_and_clear_messages(session_id)
    assert aggregated == "Single message"


@pytest.mark.asyncio
async def test_webhook_retry_idempotency() -> None:
    """Test that webhook retries don't duplicate messages."""
    store = create_mock_redis_store()
    manager = ProcessingCancellationManager(store=store)
    session_id = "test_session_3"
    
    msg_id_1 = manager.add_message_to_buffer(session_id, "Same message")
    msg_id_2 = manager.add_message_to_buffer(session_id, "Same message")
    
    assert msg_id_1 == msg_id_2, "Same message should return same ID"
    
    count = manager._get_message_count(session_id)
    assert count == 1, "Duplicate messages should not be added"


@pytest.mark.asyncio
async def test_rapid_succession_scenario() -> None:
    """Test the exact scenario described: A, wait, B, wait, process."""
    store = create_mock_redis_store()
    manager = ProcessingCancellationManager(store=store)
    session_id = "test_session_4"
    
    events: list[tuple[str, float, Any]] = []
    
    async def message_a_handler() -> str:
        events.append(("A_start", time.time(), None))
        msg_id = manager.add_message_to_buffer(session_id, "Message A")
        result = await manager.wait_for_inactivity(
            session_id=session_id,
            since_message_id=msg_id,
            inactivity_ms=1000,
            check_interval_ms=100,
        )
        events.append(("A_result", time.time(), result))
        return result
    
    async def message_b_handler() -> str:
        await asyncio.sleep(0.5)
        events.append(("B_start", time.time(), None))
        msg_id = manager.add_message_to_buffer(session_id, "Message B")
        result = await manager.wait_for_inactivity(
            session_id=session_id,
            since_message_id=msg_id,
            inactivity_ms=1000,
            check_interval_ms=100,
        )
        events.append(("B_result", time.time(), result))
        
        if result in ["process_aggregated", "process_single"]:
            aggregated = manager.get_and_clear_messages(session_id)
            events.append(("B_aggregated", time.time(), aggregated))
        
        return result
    
    start_time = time.time()
    
    task_a = asyncio.create_task(message_a_handler())
    task_b = asyncio.create_task(message_b_handler())
    
    result_a = await task_a
    result_b = await task_b
    
    total_time = time.time() - start_time
    
    assert result_a == "exit", "Message A should exit when B arrives"
    assert result_b == "process_aggregated", "Message B should process aggregated"
    
    assert total_time >= 1.5, f"Should wait at least 1.5s (0.5s delay + 1s inactivity), got {total_time:.2f}s"
    assert total_time < 2.0, f"Should not wait more than 2s, got {total_time:.2f}s"
    
    aggregated_event = [e for e in events if e[0] == "B_aggregated"]
    assert len(aggregated_event) == 1
    aggregated_text = aggregated_event[0][2]
    
    assert "Message A" in aggregated_text
    assert "Message B" in aggregated_text


@pytest.mark.asyncio
async def test_message_timestamps_in_aggregation() -> None:
    """Test that aggregated messages include relative timestamps."""
    store = create_mock_redis_store()
    manager = ProcessingCancellationManager(store=store)
    session_id = "test_session_5"
    
    manager.add_message_to_buffer(session_id, "First")
    await asyncio.sleep(0.2)
    manager.add_message_to_buffer(session_id, "Second")
    await asyncio.sleep(0.3)
    msg_id_3 = manager.add_message_to_buffer(session_id, "Third")
    
    await manager.wait_for_inactivity(
        session_id=session_id,
        since_message_id=msg_id_3,
        inactivity_ms=500,
        check_interval_ms=100,
    )
    
    aggregated = manager.get_and_clear_messages(session_id)
    
    assert aggregated is not None
    assert "First" in aggregated
    assert "Second" in aggregated
    assert "Third" in aggregated


@pytest.mark.asyncio
async def test_cleanup_after_processing() -> None:
    """Test that state is properly cleaned up after processing."""
    store = create_mock_redis_store()
    manager = ProcessingCancellationManager(store=store)
    session_id = "test_session_6"
    
    msg_id = manager.add_message_to_buffer(session_id, "Test message")
    
    count_before = manager._get_message_count(session_id)
    assert count_before == 1
    
    manager.get_and_clear_messages(session_id)
    
    count_after = manager._get_message_count(session_id)
    assert count_after == 0
    
    manager.mark_processing_complete(session_id)
    
    count_final = manager._get_message_count(session_id)
    assert count_final == 0

