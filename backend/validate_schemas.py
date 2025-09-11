#!/usr/bin/env python3
"""
Comprehensive Schema Validation Test

This script validates that all our Pydantic models can be instantiated correctly
and that the data flow through the system works properly.

Run this as part of CI/CD to catch schema issues early.
"""

import sys
from typing import Any
from unittest.mock import MagicMock


def test_tool_schemas():
    """Test that all tool schemas can be instantiated correctly."""
    print("🧪 Testing Tool Schemas...")
    
    from app.flow_core.types import (
        PerformActionCall, 
        RequestHumanHandoffCall, 
        GPT5Response
    )
    
    # Test data
    test_messages = [{"text": "Test message", "delay_ms": 0}]
    
    # Test PerformActionCall
    try:
        perform_action = PerformActionCall(
            tool_name="PerformAction",
            actions=["stay"],
            messages=test_messages,
            reasoning="Test reasoning",
            confidence=0.8
        )
        print("✅ PerformActionCall schema valid")
    except Exception as e:
        print(f"❌ PerformActionCall schema error: {e}")
        return False
    
    # Test RequestHumanHandoffCall
    try:
        handoff_call = RequestHumanHandoffCall(
            tool_name="RequestHumanHandoff",
            messages=test_messages,
            reasoning="Test handoff",
            confidence=0.9,
            reason="explicit_request",
            context_summary="User requested human assistance"
        )
        print("✅ RequestHumanHandoffCall schema valid")
    except Exception as e:
        print(f"❌ RequestHumanHandoffCall schema error: {e}")
        return False
    # Test GPT5Response
    try:
        response = GPT5Response(
            tools=[perform_action],
            reasoning="Test response reasoning"
        )
        print("✅ GPT5Response schema valid")
    except Exception as e:
        print(f"❌ GPT5Response schema error: {e}")
        return False
    
    return True


def test_responder_data_flow():
    """Test the actual data flow through the responder."""
    print("\n🧪 Testing Responder Data Flow...")
    
    try:
        from app.flow_core.services.responder import EnhancedFlowResponder
        from app.flow_core.state import FlowContext
        from unittest.mock import MagicMock, patch
        
        # Create mock LLM
        mock_llm = MagicMock()
        
        # Mock the LLM response
        mock_llm_response = {
            "content": "Test response",
            "tool_calls": [{
                "name": "PerformAction", 
                "arguments": {
                    "actions": ["stay"],
                    "reasoning": "Test reasoning",
                    "confidence": 0.8
                }
            }]
        }
        
        # Mock the _call_langchain method to return our test data
        with patch.object(EnhancedFlowResponder, '_call_langchain', return_value=mock_llm_response):
            responder = EnhancedFlowResponder(mock_llm)
            
            # Create test context
            context = FlowContext(flow_id="test_flow")
            context.current_node_id = "test_node"
            
            # Test the respond method (this is where the error occurred)
            result = responder.respond(
                prompt="Test prompt",
                pending_field=None,
                context=context,
                user_message="Test user message"
            )
            
            print("✅ Responder data flow working")
            print(f"   Tool name: {result.tool_name}")
            print(f"   Messages: {len(result.messages)} message(s)")
            return True
            
    except Exception as e:
        print(f"❌ Responder data flow error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_whatsapp_integration():
    """Test WhatsApp message processor integration."""
    print("\n🧪 Testing WhatsApp Integration...")
    
    try:
        from app.whatsapp.message_processor import WhatsAppMessageProcessor
        from app.whatsapp.twilio_adapter import TwilioWhatsAppAdapter
        from unittest.mock import MagicMock
        
        # Create mock adapter
        mock_settings = MagicMock()
        mock_settings.twilio_account_sid = 'test'
        mock_settings.twilio_auth_token = 'test'
        mock_settings.whatsapp_provider = 'twilio'
        mock_settings.debug = False
        
        adapter = TwilioWhatsAppAdapter(mock_settings)
        processor = WhatsAppMessageProcessor(adapter)
        
        # Test retry detection method
        mock_message_data = {
            "message_text": "test message",
            "sender_number": "whatsapp:+1234567890"
        }
        mock_app_context = MagicMock()
        mock_app_context.store = None
        
        is_retry = processor._is_likely_retry(mock_message_data, mock_app_context)
        print(f"✅ WhatsApp retry detection working: {is_retry}")
        
        return True
        
    except Exception as e:
        print(f"❌ WhatsApp integration error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all validation tests."""
    print("🚀 Running Comprehensive Schema Validation...")
    print("=" * 60)
    
    tests = [
        test_tool_schemas,
        test_responder_data_flow,
        test_whatsapp_integration
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All schema validation tests passed!")
        return 0
    else:
        print(f"💥 {failed} schema validation tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
