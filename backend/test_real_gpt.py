#!/usr/bin/env python3
"""Test with REAL GPT API calls and Langfuse tracing."""

import os
import sys
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from langchain.chat_models import init_chat_model
from app.core.langchain_adapter import LangChainToolsLLM
from app.core.langfuse_clean import get_tracer


def test_real_gpt_call():
    """Make a REAL GPT API call and trace it."""
    print("🤖 Making REAL GPT-5 API Call...")
    
    try:
        # Initialize GPT-5
        chat_model = init_chat_model(
            "gpt-5", 
            model_provider="openai"
        )
        llm = LangChainToolsLLM(chat_model)
        
        print("✅ GPT-5 initialized")
        
        # Test 1: Real tool calling with GPT
        print("\n🛠️  REAL GPT Tool Calling Test")
        
        from pydantic import BaseModel
        
        class PremiumPlanResponse(BaseModel):
            plan_recommendation: str
            monthly_price: int
            key_features: list[str]
            reasoning: str
        
        prompt = """
        A customer said: "I'm a small business owner with 10 employees. I need a premium plan that includes team collaboration, advanced analytics, and priority support. My budget is around $200/month."
        
        Recommend the best premium plan using the PremiumPlanResponse tool.
        """
        
        print("📡 Making REAL API call to GPT-5...")
        
        # This makes a REAL API call to OpenAI GPT-5
        result = llm.extract(prompt, [PremiumPlanResponse])
        
        print(f"    ✅ GPT-5 Response Tool: {result.get('__tool_name__', 'No tool')}")
        if 'plan_recommendation' in result:
            print(f"    💼 Plan: {result['plan_recommendation']}")
        if 'monthly_price' in result:
            print(f"    💰 Price: ${result['monthly_price']}/month")
        if 'reasoning' in result:
            print(f"    🧠 GPT Reasoning: {result['reasoning'][:150]}...")
        
        # Test 2: Real text rewriting with GPT
        print("\n✏️  REAL GPT Text Rewriting")
        
        original = "Hello! We have received your premium plan inquiry. Please provide additional details about your requirements."
        instruction = "Rewrite this to sound more conversational and enthusiastic, like a helpful sales assistant"
        
        print("📡 Making REAL rewrite call to GPT-5...")
        
        # This makes a REAL API call to OpenAI GPT-5
        rewritten = llm.rewrite(instruction, original)
        
        print(f"    📝 Original: {original}")
        print(f"    ✨ GPT-5 Rewrite: {rewritten}")
        
        return True
        
    except Exception as e:
        print(f"    ❌ Error: {e}")
        print("    💡 Make sure you have OPENAI_API_KEY set in your .env")
        return False


def test_manual_gpt_tracing():
    """Manual tracing of a real GPT call."""
    print("\n🔧 Manual GPT Tracing Test")
    
    tracer = get_tracer()
    
    if not tracer.is_enabled():
        print("    ⚠️  Langfuse not enabled")
        return False
    
    try:
        # Initialize GPT-5
        chat_model = init_chat_model("gpt-5", model_provider="openai")
        
        input_text = "You are a premium subscription expert. Explain the top 3 benefits of upgrading to a premium plan for a small business owner."
        
        print("📡 Making REAL GPT-5 call...")
        
        # Make the actual GPT API call
        response = chat_model.invoke(input_text)
        output_text = response.content if hasattr(response, 'content') else str(response)
        
        print(f"    🤖 GPT-5 Response Length: {len(output_text)} characters")
        print(f"    📝 Preview: {output_text[:200]}...")
        
        # Manually trace the REAL GPT call
        tracer.trace_llm_call(
            name="real_gpt5_premium_advice",
            model="gpt-5",
            input_text=input_text,
            output_text=output_text,
            metadata={
                "operation": "real_gpt_call",
                "api_provider": "openai",
                "use_case": "premium_consultation",
                "response_length": len(output_text),
            },
            user_id="real_gpt_test_user",
            session_id="real_gpt_session",
        )
        
        print("    ✅ REAL GPT call traced to Langfuse")
        
        tracer.flush()
        return True
        
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return False


def test_gpt_conversation_flow():
    """Test a multi-turn conversation with GPT."""
    print("\n💬 GPT Conversation Flow Test")
    
    try:
        chat_model = init_chat_model("gpt-5", model_provider="openai")
        tracer = get_tracer()
        
        # Conversation turns
        conversations = [
            "I'm interested in upgrading my business plan",
            "We have about 15 employees and need team collaboration features", 
            "What's the price difference between your standard and premium plans?"
        ]
        
        for i, user_input in enumerate(conversations, 1):
            print(f"    👤 Turn {i}: {user_input}")
            
            # Make real GPT call
            response = chat_model.invoke(f"Customer says: '{user_input}'. Respond as a helpful sales assistant.")
            gpt_output = response.content if hasattr(response, 'content') else str(response)
            
            print(f"    🤖 GPT: {gpt_output[:100]}...")
            
            # Trace each turn
            if tracer.is_enabled():
                tracer.trace_llm_call(
                    name=f"conversation_turn_{i}",
                    model="gpt-5",
                    input_text=user_input,
                    output_text=gpt_output,
                    metadata={
                        "turn_number": i,
                        "conversation_type": "sales_consultation",
                        "api_provider": "openai",
                    },
                    user_id="conversation_test_user",
                    session_id="conversation_session_123",
                )
        
        if tracer.is_enabled():
            tracer.flush()
            print("    ✅ Full conversation traced")
        
        return True
        
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return False


def main():
    """Run real GPT tests."""
    print("🚀 REAL GPT-5 API Test with Langfuse Tracing")
    print("This will make ACTUAL API calls to OpenAI!")
    print("=" * 50)
    
    # Check environment variables
    required_vars = ["OPENAI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("\n💡 Add to your .env file:")
        for var in missing_vars:
            if var == "OPENAI_API_KEY":
                print(f"  {var}=sk-your_openai_key_here")
            elif var == "LANGFUSE_HOST":
                print(f"  {var}=https://us.cloud.langfuse.com")
            else:
                print(f"  {var}=your_langfuse_key_here")
        return False
    
    print("✅ All environment variables found")
    print("💰 WARNING: This will use your OpenAI API credits")
    print("🔥 Making REAL API calls to GPT-5 + tracing to Langfuse...\n")
    
    # Run tests
    tests = [
        test_real_gpt_call,
        test_manual_gpt_tracing, 
        test_gpt_conversation_flow,
    ]
    
    passed = 0
    total_tests = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ {test.__name__} failed")
        except Exception as e:
            print(f"❌ {test.__name__} error: {e}")
    
    print(f"\n📊 Results: {passed}/{total_tests} tests passed")
    
    if passed > 0:
        print("\n🎉 REAL GPT-5 calls were made and traced!")
        print("💸 API credits were used for actual OpenAI calls")
        print("📊 Check your Langfuse dashboard for:")
        print("  • REAL GPT-5 responses")
        print("  • Actual tool calling with structured output")
        print("  • Real conversation flows")
        print("  • Authentic processing times and token usage")
        print(f"  🔗 Dashboard: {os.getenv('LANGFUSE_HOST')}")
        
        print("\n🔍 Look for these traces:")
        print("  • Tool: PremiumPlanResponse")
        print("  • real_gpt5_premium_advice")
        print("  • conversation_turn_1, conversation_turn_2, conversation_turn_3")
        
        return True
    else:
        print("❌ All GPT tests failed")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
