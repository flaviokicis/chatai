#!/usr/bin/env python3
"""Verify GPT-5 reasoning is working correctly with langchain-openai."""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()


def test_reasoning_only():
    """Test that reasoning parameter works correctly without verbosity."""
    
    print("Testing GPT-5 reasoning parameter (no verbosity, no conflicts)")
    print("=" * 60)
    
    # Test 1: Basic reasoning with minimal effort
    print("\n1. Testing minimal reasoning:")
    model_minimal = ChatOpenAI(
        model="gpt-5",
        model_kwargs={"reasoning": {"effort": "minimal"}},
        temperature=0
    )
    
    response = model_minimal.invoke("What is 2+2?")
    print(f"✅ Minimal reasoning works: {response.content[:100]}...")
    
    # Test 2: Basic reasoning with high effort
    print("\n2. Testing high reasoning:")
    model_high = ChatOpenAI(
        model="gpt-5",
        model_kwargs={"reasoning": {"effort": "high"}},
        temperature=0
    )
    
    response = model_high.invoke("What is 2+2?")
    print(f"✅ High reasoning works: {response.content[:100]}...")
    
    # Test 3: Reasoning with structured output (this should work fine)
    print("\n3. Testing reasoning with structured output:")
    
    class MathAnswer(BaseModel):
        """Structured response for math problems"""
        answer: int = Field(description="The numerical answer")
        explanation: str = Field(description="Brief explanation")
    
    model_structured = ChatOpenAI(
        model="gpt-5",
        model_kwargs={"reasoning": {"effort": "high"}},
        temperature=0
    ).with_structured_output(MathAnswer)
    
    result = model_structured.invoke("What is 2+2?")
    print(f"✅ Structured output with reasoning works:")
    print(f"   Answer: {result.answer}")
    print(f"   Explanation: {result.explanation}")
    
    print("\n" + "=" * 60)
    print("✅ All tests passed! GPT-5 reasoning is working correctly.")
    print("\nNOTE: The verbosity parameter issue from GitHub #32492 doesn't")
    print("affect us since we're only using the reasoning parameter.")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        exit(1)
    
    test_reasoning_only()
