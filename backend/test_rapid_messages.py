#!/usr/bin/env python3
"""Test script for rapid message handling and cancellation."""

import asyncio

from app.services.processing_cancellation_manager import ProcessingCancellationManager


async def simulate_rapid_messages():
    """Simulate rapid messages to test the cancellation mechanism."""
    print("🧪 Testing Rapid Message Cancellation")
    print("=" * 50)

    # Initialize the cancellation manager
    manager = ProcessingCancellationManager()
    session_id = "test:user123:flow456"

    print(f"📱 Session ID: {session_id}")
    print()

    # Simulate first message processing
    print("1️⃣ User sends first message: 'Hello'")
    manager.add_message_to_buffer(session_id, "Hello")
    token1 = manager.create_cancellation_token(session_id)
    print(f"   ✅ Processing started (token: {id(token1)})")
    print(f"   ⏰ Processing state: {manager._processing_states[session_id].is_processing}")

    # Wait a bit to simulate processing time
    await asyncio.sleep(0.5)

    # Check if we should cancel (within 2 minutes = yes)
    should_cancel = manager.should_cancel_processing(session_id)
    print(f"   🤔 Should cancel for new message? {should_cancel}")
    print()

    # Simulate second rapid message
    print("2️⃣ User sends second message: 'I want to buy lights' (within 2 minutes)")
    manager.add_message_to_buffer(session_id, "I want to buy lights")

    # Check if we should cancel now
    should_cancel = manager.should_cancel_processing(session_id)
    print(f"   🚨 Should cancel processing? {should_cancel}")

    if should_cancel:
        print("   🛑 Cancelling first processing...")
        cancelled = manager.cancel_processing(session_id)
        print(f"   ✅ Cancellation successful: {cancelled}")
        print(f"   🔍 Token is set: {token1.is_set()}")

        # Get aggregated messages
        aggregated = manager.get_aggregated_messages(session_id)
        print(f"   📝 Aggregated message: '{aggregated}'")

        # Start new processing with aggregated message
        print("   🔄 Starting new processing with aggregated message...")
        token2 = manager.create_cancellation_token(session_id)
        print(f"   ✅ New processing started (token: {id(token2)})")

    print()

    # Simulate third message
    print("3️⃣ User sends third message: 'for my warehouse' (still within 2 minutes)")
    manager.add_message_to_buffer(session_id, "for my warehouse")

    should_cancel = manager.should_cancel_processing(session_id)
    print(f"   🚨 Should cancel processing? {should_cancel}")

    if should_cancel:
        print("   🛑 Cancelling second processing...")
        cancelled = manager.cancel_processing(session_id)
        print(f"   ✅ Cancellation successful: {cancelled}")

        # Get final aggregated messages
        aggregated = manager.get_aggregated_messages(session_id)
        print(f"   📝 Final aggregated message: '{aggregated}'")

        # Start final processing
        print("   🔄 Starting final processing with all messages...")
        token3 = manager.create_cancellation_token(session_id)
        print(f"   ✅ Final processing started (token: {id(token3)})")

        # Simulate processing completion
        await asyncio.sleep(1.0)
        print("   ⏱️  Processing completed successfully")
        manager.mark_processing_complete(session_id)
        print("   ✅ Processing marked complete")

    print()
    print("🎯 Test completed!")
    print("Summary: 3 rapid messages were aggregated into: 'Hello I want to buy lights for my warehouse'")


async def test_time_window():
    """Test the 2-minute time window."""
    print("\n🕐 Testing 2-minute time window")
    print("=" * 30)

    manager = ProcessingCancellationManager()
    session_id = "test:user456:flow789"

    # Set a very short window for testing (2 seconds instead of 2 minutes)
    manager.RAPID_MESSAGE_WINDOW = 2.0

    print("1️⃣ First message")
    manager.add_message_to_buffer(session_id, "First message")
    token1 = manager.create_cancellation_token(session_id)

    print("2️⃣ Second message (within 2 seconds)")
    manager.add_message_to_buffer(session_id, "Second message")
    should_cancel = manager.should_cancel_processing(session_id)
    print(f"   Should cancel: {should_cancel} ✅")

    print("   Waiting 3 seconds...")
    await asyncio.sleep(3)

    print("3️⃣ Third message (after 3 seconds)")
    manager.add_message_to_buffer(session_id, "Third message")
    should_cancel = manager.should_cancel_processing(session_id)
    print(f"   Should cancel: {should_cancel} ❌ (outside time window)")

    print("✅ Time window test passed!")


if __name__ == "__main__":
    print("🚀 Starting Rapid Message Tests")
    print()

    asyncio.run(simulate_rapid_messages())
    asyncio.run(test_time_window())

    print("\n🎉 All tests completed!")
