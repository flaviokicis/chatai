"""
Integration test for Redis key consistency and predictability.

This test ensures that all Redis key patterns are consistent and that
the centralized key builder works reliably for all data types.
"""

import json
from datetime import datetime
from uuid import uuid4

import pytest
import redis

from app.core.state import RedisStore
from app.flow_core.state import FlowContext
from app.services.session_manager import RedisSessionManager


class TestRedisKeyConsistency:
    """Test Redis key consistency across all data types and operations."""

    @pytest.fixture
    def redis_client(self):
        """Redis client for testing."""
        client = redis.from_url("redis://localhost:6379")
        # Use a test namespace to avoid conflicts
        yield client
        # Cleanup test keys
        test_keys = client.keys("test_chatai:*")
        if test_keys:
            client.delete(*test_keys)

    @pytest.fixture
    def test_store(self):
        """Test Redis store with test namespace."""
        return RedisStore("redis://localhost:6379", namespace="test_chatai")

    @pytest.fixture
    def test_key_builder(self):
        """Test key builder with test namespace."""
        from app.core.redis_keys import RedisKeyBuilder
        return RedisKeyBuilder(namespace="test_chatai")

    def test_conversation_state_key_consistency(self, test_key_builder, test_store, redis_client):
        """Test that conversation state keys are consistent between storage and retrieval."""

        # Test data
        user_id = "whatsapp:5522988544370"
        session_id = "flow:whatsapp:5522988544370:flow.atendimento_luminarias"
        test_data = {"test": "data", "timestamp": datetime.now().isoformat()}

        # === STORAGE ===
        storage_key = test_key_builder.conversation_state_key(user_id, session_id)
        print(f"Storage key: {storage_key}")

        # Store using the RedisStore (simulates actual usage)
        test_store.save(user_id, session_id, test_data)

        # Verify the actual Redis key matches our expected pattern
        actual_key = test_store._state_key(user_id, session_id)
        assert actual_key == storage_key, f"Storage key mismatch: {actual_key} != {storage_key}"

        # === RETRIEVAL ===
        retrieved_data = test_store.load(user_id, session_id)
        assert retrieved_data == test_data, "Data retrieval failed"

        # === CLEANUP ===
        cleanup_patterns = test_key_builder.get_conversation_patterns(user_id, "flow.atendimento_luminarias")
        deleted_keys = 0

        for pattern in cleanup_patterns:
            if "*" in pattern:
                keys = redis_client.keys(pattern)
                if keys:
                    deleted_keys += redis_client.delete(*keys)
            elif redis_client.exists(pattern):
                deleted_keys += redis_client.delete(pattern)

        assert deleted_keys > 0, "Cleanup patterns should match and delete stored keys"

        # Verify data is actually deleted
        assert test_store.load(user_id, session_id) is None, "Data should be deleted after cleanup"

    def test_meta_key_consistency(self, test_key_builder, test_store, redis_client):
        """Test meta key consistency for session timing."""

        user_id = "whatsapp:5522988544370"
        agent_type = "flow"
        meta_data = {
            "last_inbound_ts": "2025-08-31T07:34:18",
            "window_start_ts": "2025-08-31T07:30:00"
        }

        # === STORAGE ===
        meta_key = test_key_builder.conversation_meta_key(user_id, agent_type)
        print(f"Meta key: {meta_key}")

        # Store meta data (simulates WindowedSessionPolicy usage)
        test_store.save(user_id, f"meta:{agent_type}", meta_data)

        # === RETRIEVAL ===
        retrieved_meta = test_store.load(user_id, f"meta:{agent_type}")
        assert retrieved_meta == meta_data, "Meta data retrieval failed"

        # === CLEANUP ===
        cleanup_patterns = test_key_builder.get_conversation_patterns(user_id, None)
        deleted_keys = 0

        for pattern in cleanup_patterns:
            if "*" in pattern:
                keys = redis_client.keys(pattern)
                if keys:
                    deleted_keys += redis_client.delete(*keys)

        assert deleted_keys > 0, "Meta cleanup should work"
        assert test_store.load(user_id, f"meta:{agent_type}") is None, "Meta data should be deleted"

    def test_current_reply_key_consistency(self, test_key_builder, test_store, redis_client):
        """Test current reply key consistency for interruption handling."""

        user_id = "whatsapp:5522988544370"
        reply_data = {"reply_id": str(uuid4()), "timestamp": int(datetime.now().timestamp())}

        # === STORAGE ===
        current_reply_key = test_key_builder.current_reply_key(user_id)
        print(f"Current reply key: {current_reply_key}")

        # Store reply data (simulates message processor usage)
        key_suffix = current_reply_key.replace("test_chatai:state:system:", "")
        test_store.save("system", key_suffix, reply_data)

        # === RETRIEVAL ===
        retrieved_reply = test_store.load("system", key_suffix)
        assert retrieved_reply == reply_data, "Reply data retrieval failed"

        # === CLEANUP ===
        cleanup_patterns = test_key_builder.get_conversation_patterns(user_id, None)
        deleted_keys = 0

        for pattern in cleanup_patterns:
            if "*" in pattern:
                keys = redis_client.keys(pattern)
                if keys:
                    deleted_keys += redis_client.delete(*keys)
            elif redis_client.exists(pattern):
                deleted_keys += redis_client.delete(pattern)

        assert deleted_keys > 0, "Current reply cleanup should work"
        assert test_store.load("system", key_suffix) is None, "Reply data should be deleted"

    def test_flow_context_full_lifecycle(self, test_key_builder, test_store, redis_client):
        """Test complete flow context lifecycle: create, store, retrieve, cleanup."""

        user_id = "whatsapp:5522988544370"
        flow_id = "flow.atendimento_luminarias"

        # === CREATE FLOW CONTEXT ===
        ctx = FlowContext(flow_id=flow_id)
        ctx.user_id = user_id
        ctx.add_turn("user", "Quero comprar LEDs", "q.interesse_inicial")
        ctx.add_turn("assistant", "Entendido! Qual é o seu interesse?", "q.interesse_inicial")
        ctx.answers["interesse_inicial"] = "comprar LEDs pro meu posto de gasolina"

        # === STORAGE ===
        session_id = f"flow:{user_id}:{flow_id}"
        storage_key = test_key_builder.conversation_state_key(user_id, session_id)
        print(f"Flow context key: {storage_key}")

        test_store.save(user_id, session_id, ctx.to_dict())

        # === RETRIEVAL ===
        retrieved_data = test_store.load(user_id, session_id)
        assert retrieved_data is not None, "Flow context should be retrievable"
        assert retrieved_data["flow_id"] == flow_id, "Flow ID should match"
        assert len(retrieved_data["history"]) == 2, "History should have 2 turns"
        assert retrieved_data["answers"]["interesse_inicial"] == "comprar LEDs pro meu posto de gasolina"

        # Test context reconstruction
        restored_ctx = FlowContext.from_dict(retrieved_data)
        assert restored_ctx.flow_id == flow_id
        assert len(restored_ctx.history) == 2
        assert restored_ctx.answers["interesse_inicial"] == "comprar LEDs pro meu posto de gasolina"

        # === CLEANUP ===
        cleanup_patterns = test_key_builder.get_conversation_patterns(user_id, flow_id)
        deleted_keys = 0

        for pattern in cleanup_patterns:
            if "*" in pattern:
                keys = redis_client.keys(pattern)
                if keys:
                    deleted_keys += redis_client.delete(*keys)
            elif redis_client.exists(pattern):
                deleted_keys += redis_client.delete(pattern)

        assert deleted_keys > 0, "Flow context cleanup should work"
        assert test_store.load(user_id, session_id) is None, "Flow context should be deleted"

    def test_session_manager_integration(self, test_store, redis_client):
        """Test that session managers use consistent key patterns."""

        user_id = "whatsapp:5522988544370"
        flow_id = "flow.atendimento_luminarias"

        # === SESSION MANAGER ===
        session_mgr = RedisSessionManager(test_store)
        session_id = session_mgr.create_session(user_id, flow_id)

        print(f"Session manager created session_id: {session_id}")

        # Test context storage
        ctx = FlowContext(flow_id=flow_id)
        ctx.user_id = user_id
        ctx.add_turn("user", "Test message", None)

        session_mgr.save_context(session_id, ctx)

        # Test context retrieval
        retrieved_ctx = session_mgr.load_context(session_id)
        assert retrieved_ctx is not None, "Context should be retrievable"
        assert retrieved_ctx.flow_id == flow_id
        assert len(retrieved_ctx.history) == 1

        # Test context clearing
        session_mgr.clear_context(session_id)
        cleared_ctx = session_mgr.load_context(session_id)
        assert cleared_ctx is None, "Context should be cleared"

    def test_all_data_types_comprehensive(self, test_key_builder, test_store, redis_client):
        """Comprehensive test of all Redis data patterns used in the application."""

        user_id = "whatsapp:5522988544370"
        flow_id = "flow.atendimento_luminarias"

        # === ALL DATA TYPES ===
        test_data = {
            # Conversation state
            "conversation_state": {
                "key": test_key_builder.conversation_state_key(user_id, f"flow:{user_id}:{flow_id}"),
                "data": {"flow_id": flow_id, "answers": {"test": "value"}}
            },
            # Meta data
            "meta": {
                "key": test_key_builder.conversation_meta_key(user_id, "flow"),
                "data": {"last_inbound_ts": "2025-08-31T07:34:18", "window_start_ts": "2025-08-31T07:30:00"}
            },
            # Current reply
            "current_reply": {
                "key": test_key_builder.current_reply_key(user_id),
                "data": {"reply_id": str(uuid4()), "timestamp": int(datetime.now().timestamp())}
            }
        }

        # === STORE ALL DATA TYPES ===
        for data_type, info in test_data.items():
            print(f"Storing {data_type}: {info['key']}")

            if data_type == "current_reply":
                # Current reply uses system namespace
                key_suffix = info["key"].replace("test_chatai:state:system:", "")
                test_store.save("system", key_suffix, info["data"])
            elif data_type == "meta":
                # Meta uses meta: prefix
                test_store.save(user_id, "meta:flow", info["data"])
            else:
                # Regular conversation state
                session_id = f"flow:{user_id}:{flow_id}"
                test_store.save(user_id, session_id, info["data"])

        # === VERIFY ALL DATA EXISTS ===
        for data_type, info in test_data.items():
            exists = redis_client.exists(info["key"])
            assert exists, f"{data_type} key should exist: {info['key']}"

        # === TEST CLEANUP PATTERNS ===
        cleanup_patterns = test_key_builder.get_conversation_patterns(user_id, flow_id)
        print(f"Testing {len(cleanup_patterns)} cleanup patterns")

        total_deleted = 0
        for pattern in cleanup_patterns:
            if "*" in pattern:
                keys = redis_client.keys(pattern)
                if keys:
                    deleted = redis_client.delete(*keys)
                    total_deleted += deleted
                    print(f"Pattern {pattern} deleted {deleted} keys")
            elif redis_client.exists(pattern):
                redis_client.delete(pattern)
                total_deleted += 1
                print(f"Direct key {pattern} deleted")

        assert total_deleted >= len(test_data), f"Should delete at least {len(test_data)} keys, deleted {total_deleted}"

        # === VERIFY ALL DATA DELETED ===
        for data_type, info in test_data.items():
            exists = redis_client.exists(info["key"])
            assert not exists, f"{data_type} key should be deleted: {info['key']}"

        print(f"✅ All {len(test_data)} data types: stored → retrieved → cleaned up successfully")

    def test_key_structure_predictability(self, test_key_builder):
        """Test that same inputs always produce same key structures."""

        # Test multiple users with same flow
        users = ["whatsapp:5522988544370", "whatsapp:+15550002222", "telegram:user123"]
        flow_id = "flow.atendimento_luminarias"

        for user_id in users:
            session_id = f"flow:{user_id}:{flow_id}"

            # Test conversation state key structure
            state_key = test_key_builder.conversation_state_key(user_id, session_id)
            expected_pattern = f"test_chatai:state:{user_id}:{session_id}"
            assert state_key == expected_pattern, f"State key structure mismatch for {user_id}"

            # Test meta key structure
            meta_key = test_key_builder.conversation_meta_key(user_id, "flow")
            expected_meta = f"test_chatai:state:{user_id}:meta:flow"
            assert meta_key == expected_meta, f"Meta key structure mismatch for {user_id}"

            # Test current reply key structure
            reply_key = test_key_builder.current_reply_key(user_id)
            expected_reply = f"test_chatai:state:system:current_reply:{user_id}"
            assert reply_key == expected_reply, f"Reply key structure mismatch for {user_id}"

            # Test history key structure
            history_key = test_key_builder.conversation_history_key(session_id)
            expected_history = f"test_chatai:history:{session_id}"
            assert history_key == expected_history, f"History key structure mismatch for {user_id}"

        print(f"✅ Key structures are predictable for {len(users)} different users")

    def test_cleanup_patterns_match_storage(self, test_key_builder, redis_client):
        """Test that cleanup patterns always match storage patterns."""

        test_cases = [
            {
                "user_id": "whatsapp:5522988544370",
                "flow_id": "flow.atendimento_luminarias",
                "session_id": "flow:whatsapp:5522988544370:flow.atendimento_luminarias"
            },
            {
                "user_id": "whatsapp:+15550002222",
                "flow_id": "flow.sales_qualifier",
                "session_id": "flow:whatsapp:+15550002222:flow.sales_qualifier"
            },
            {
                "user_id": "telegram:user123",
                "flow_id": "flow.support",
                "session_id": "flow:telegram:user123:flow.support"
            }
        ]

        for case in test_cases:
            # Create storage key
            storage_key = test_key_builder.conversation_state_key(case["user_id"], case["session_id"])

            # Create test data in Redis
            redis_client.set(storage_key, json.dumps({"test": "data"}), ex=60)

            # Get cleanup patterns
            cleanup_patterns = test_key_builder.get_conversation_patterns(case["user_id"], case["flow_id"])

            # Test if cleanup patterns match storage
            found_match = False
            for pattern in cleanup_patterns:
                if "*" in pattern:
                    matches = redis_client.keys(pattern)
                    if storage_key.encode() in matches:
                        found_match = True
                        break
                elif pattern == storage_key:
                    found_match = True
                    break

            assert found_match, f"Cleanup patterns should match storage key: {storage_key}"

            # Cleanup
            redis_client.delete(storage_key)

        print(f"✅ Cleanup patterns match storage for {len(test_cases)} test cases")


if __name__ == "__main__":
    # Run tests directly for quick verification
    import os
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

    test_instance = TestRedisKeyConsistency()

    # Setup fixtures manually for direct execution
    redis_client = redis.from_url("redis://localhost:6379")
    test_store = RedisStore("redis://localhost:6379", namespace="test_chatai")
    from app.core.redis_keys import RedisKeyBuilder
    test_key_builder = RedisKeyBuilder(namespace="test_chatai")

    try:
        print("=== Redis Key Consistency Integration Test ===")

        print("\n1. Testing conversation state key consistency...")
        test_instance.test_conversation_state_key_consistency(test_key_builder, test_store, redis_client)

        print("\n2. Testing meta key consistency...")
        test_instance.test_meta_key_consistency(test_key_builder, test_store, redis_client)

        print("\n3. Testing current reply key consistency...")
        test_instance.test_current_reply_key_consistency(test_key_builder, test_store, redis_client)

        print("\n4. Testing key structure predictability...")
        test_instance.test_key_structure_predictability(test_key_builder)

        print("\n5. Testing cleanup patterns match storage...")
        test_instance.test_cleanup_patterns_match_storage(test_key_builder, redis_client)

        print("\n🎯 ALL TESTS PASSED! Redis key consistency is guaranteed.")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup any remaining test keys
        test_keys = redis_client.keys("test_chatai:*")
        if test_keys:
            redis_client.delete(*test_keys)
            print(f"Cleaned up {len(test_keys)} test keys")
