#!/usr/bin/env python3
"""
Type validation tests to catch runtime errors before they happen.
Run this as part of validation to catch attribute and type mismatches.
"""

import sys


def test_flow_compilation():
    """Test that flow compilation types work correctly."""
    from app.flow_core.compiler import FlowCompiler
    from app.flow_core.ir import Flow

    # Test dict to Flow conversion
    test_flow_dict = {
        "id": "test_flow",
        "entry": "start",
        "nodes": [{"id": "start", "kind": "Terminal", "content": "Test complete"}],
        "edges": [],
    }

    try:
        # This should work - creating Flow from dict
        flow_obj = Flow.model_validate(test_flow_dict)
        assert hasattr(flow_obj, "node_by_id"), "Flow object missing node_by_id method"
        print("✅ Flow object creation from dict: OK")
    except Exception as e:
        print(f"❌ Flow object creation failed: {e}")
        return False

    # Test that compiler expects Flow object, not dict
    compiler = FlowCompiler()
    try:
        # This should fail if we pass dict directly (but we're catching it now)
        # compiler.compile(test_flow_dict)  # Would fail with AttributeError
        compiled = compiler.compile(flow_obj)  # Should work
        print("✅ Flow compilation with Flow object: OK")
    except Exception as e:
        print(f"❌ Flow compilation failed: {e}")
        return False

    return True


def test_flow_response_attributes():
    """Test FlowResponse has correct attributes."""
    from app.core.flow_response import FlowProcessingResult, FlowResponse

    # Create a test response
    response = FlowResponse(
        result=FlowProcessingResult.CONTINUE,
        message="Test message",
        metadata={"messages": [{"text": "Test", "delay_ms": 0}]},
    )

    # Check attributes
    assert hasattr(response, "message"), "FlowResponse missing 'message' attribute"
    assert not hasattr(response, "messages"), "FlowResponse should not have 'messages' attribute"
    assert hasattr(response, "metadata"), "FlowResponse missing 'metadata' attribute"

    print("✅ FlowResponse attributes: OK")
    return True


def test_type_conversions():
    """Test critical type conversions that cause runtime errors."""
    errors = []

    # Test 1: Dict to Flow conversion
    from app.flow_core.ir import Flow

    test_dict = {
        "id": "test",
        "entry": "start",
        "nodes": [{"id": "start", "kind": "Terminal", "content": "Test"}],
        "edges": [],
    }
    try:
        flow = Flow.model_validate(test_dict)
        if not hasattr(flow, "node_by_id"):
            errors.append("Flow object missing node_by_id method")
    except Exception as e:
        errors.append(f"Flow creation failed: {e}")

    # Test 2: FlowResponse structure
    from app.core.flow_response import FlowProcessingResult, FlowResponse

    response = FlowResponse(result=FlowProcessingResult.CONTINUE, message="Test")
    if hasattr(response, "messages"):
        errors.append("FlowResponse should have 'message', not 'messages'")

    # Test 3: RedisStore vs Redis
    # RedisSessionManager expects ConversationStore (RedisStore), not raw Redis

    if errors:
        for error in errors:
            print(f"❌ {error}")
        return False

    print("✅ All type conversions: OK")
    return True


def main():
    """Run all type validation tests."""
    print("🔍 Running type validation tests...")
    print("=" * 40)

    all_passed = True

    # Run tests
    tests = [
        ("Flow Compilation", test_flow_compilation),
        ("FlowResponse Attributes", test_flow_response_attributes),
        ("Type Conversions", test_type_conversions),
    ]

    for test_name, test_func in tests:
        print(f"\nTesting {test_name}...")
        try:
            if not test_func():
                all_passed = False
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("✅ All type validation tests passed!")
        return 0
    print("❌ Some type validation tests failed!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
