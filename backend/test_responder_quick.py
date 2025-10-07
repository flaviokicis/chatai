#!/usr/bin/env python3
"""
Quick smoke test for responder after prompt refactoring.
"""

import sys
sys.path.insert(0, '/Users/jessica/me/chatai/backend')

from app.flow_core.services.responder import EnhancedFlowResponder
from app.flow_core.state import FlowContext
from uuid import uuid4, UUID


def test_prompt_building():
    """Test that prompt building still works."""
    
    print("🧪 Testing EnhancedFlowResponder prompt building...")
    
    # Mock LLM client
    class MockLLM:
        def extract(self, instruction, tools):
            # Just verify the instruction was built
            return {
                "tool_calls": [{
                    "name": "PerformAction",
                    "arguments": {
                        "actions": ["stay"],
                        "messages": [{"text": "Test response", "delay_ms": 0}],
                        "reasoning": "Test",
                        "confidence": 0.9
                    }
                }],
                "content": ""
            }
    
    llm = MockLLM()
    responder = EnhancedFlowResponder(llm=llm, thought_tracer=None)
    
    # Create test context
    ctx = FlowContext(
        flow_id="test-flow",
        user_id="test-user",
        session_id=str(uuid4()),
        tenant_id=UUID("068b37cd-c090-710d-b0b6-5ca37c2887ff"),
        current_node_id="test-node",
    )
    
    # Build instruction (this will use the shared prompts)
    instruction = responder._build_gpt5_instruction(
        prompt="Test prompt",
        pending_field=None,
        context=ctx,
        user_message="Test message",
        allowed_values=None,
        project_context=None,
        is_completion=False,
        available_edges=None,
        is_admin=False,
        flow_graph=None
    )
    
    # Verify key sections are present
    checks = {
        "Core Identity": "RESPONSIBLE ATTENDANT" in instruction,
        "Information Boundaries": "INFORMATION BOUNDARIES" in instruction,
        "Never Invent Constraint": "NEVER INVENT QUESTIONS" in instruction,
        "CEP Example": "CEP" in instruction,
        "Golden Rule": "REGRA DE OURO" in instruction,
        "Identity & Style": "IDENTITY & STYLE" in instruction,
        "RAG Section": "RAG-RETRIEVED INFORMATION" in instruction,
        "Flow Graph": "DEFINIÇÃO COMPLETA DO FLUXO" in instruction,
        "Escalation": "actions=['handoff']" in instruction or "actions=[" in instruction,
    }
    
    print("\n✅ Prompt Building Works!")
    print("\nKey Sections Present:")
    all_passed = True
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check_name}")
        if not passed:
            all_passed = False
    
    print(f"\nTotal instruction length: {len(instruction)} characters")
    
    if all_passed:
        print("\n✅ ALL CHECKS PASSED - Responder prompt is working correctly!")
        return True
    else:
        print("\n❌ SOME CHECKS FAILED - Review the prompt!")
        return False


if __name__ == "__main__":
    try:
        success = test_prompt_building()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
