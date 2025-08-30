#!/usr/bin/env python
"""
Test script to verify direct intention routing works on first interaction.
Tests the fix for the bug where first user messages were not processed.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.flow_core.runner import FlowTurnRunner
from app.flow_core.compiler import compile_flow
from app.core.llm import init_llm
import json

def test_direct_intent():
    """Test that user can state intent directly without initial greeting."""
    
    # Load the luminarias flow
    flow_path = "playground/fluxo_luminarias.json"
    with open(flow_path, 'r') as f:
        flow_def = json.load(f)
    
    # Compile the flow
    compiled_flow = compile_flow(flow_def)
    
    # Initialize LLM and runner
    llm = init_llm("gpt-4o-mini", "openai")
    runner = FlowTurnRunner(compiled_flow, llm)
    
    # Initialize context
    ctx = runner.initialize_context()
    
    # Test 1: Direct gas station intent
    print("=" * 60)
    print("TEST 1: Direct gas station intent on first message")
    print("=" * 60)
    user_message = "Ola quero comprar luminarias pro meu posto de gasolina"
    print(f"User: {user_message}")
    
    result = runner.process_turn(ctx, user_message)
    
    print(f"Assistant: {result.assistant_message}")
    print(f"Extracted answers: {result.answers_diff}")
    print(f"Current node: {ctx.current_node_id}")
    print(f"Tool used: {result.tool_name}")
    
    # Verify the intent was extracted
    assert ctx.answers.get('interesse_inicial') is not None, \
        "Failed to extract interesse_inicial from first message!"
    
    # Verify we've advanced past the initial question
    assert ctx.current_node_id != 'q.interesse_inicial', \
        f"Still stuck on initial question! Current node: {ctx.current_node_id}"
    
    print("\n✅ Test 1 PASSED: Intent extracted and flow advanced on first message")
    
    # Test 2: Different direct intent
    print("\n" + "=" * 60)
    print("TEST 2: Direct sports court intent on first message")
    print("=" * 60)
    
    # Reset context for new test
    ctx = runner.initialize_context()
    user_message = "Preciso de iluminação para minha quadra de tênis"
    print(f"User: {user_message}")
    
    result = runner.process_turn(ctx, user_message)
    
    print(f"Assistant: {result.assistant_message}")
    print(f"Extracted answers: {result.answers_diff}")
    print(f"Current node: {ctx.current_node_id}")
    print(f"Tool used: {result.tool_name}")
    
    # Verify the intent was extracted
    assert ctx.answers.get('interesse_inicial') is not None, \
        "Failed to extract interesse_inicial from tennis court message!"
    
    # Verify we've advanced past the initial question
    assert ctx.current_node_id != 'q.interesse_inicial', \
        f"Still stuck on initial question! Current node: {ctx.current_node_id}"
    
    print("\n✅ Test 2 PASSED: Tennis court intent extracted and flow advanced")
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED! 🎉")
    print("Direct intention routing is working correctly!")
    print("=" * 60)

if __name__ == "__main__":
    test_direct_intent()

