#!/usr/bin/env python3
"""Test GPT-5 reasoning capabilities with langchain-openai."""

import asyncio
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Load environment variables
load_dotenv()


async def test_gpt5_reasoning():
    """Test GPT-5 with different reasoning effort levels."""

    # Test with minimal reasoning effort
    print("=" * 60)
    print("Testing GPT-5 with MINIMAL reasoning effort")
    print("=" * 60)

    try:
        model_minimal = ChatOpenAI(
            model="gpt-5", model_kwargs={"reasoning": {"effort": "minimal"}}, temperature=0
        )

        response = await model_minimal.ainvoke("What is 2+2? Please show your reasoning process.")
        print(f"Response: {response.content}")

        # Check if reasoning_content is available
        if hasattr(response, "response_metadata"):
            metadata = response.response_metadata
            if "reasoning_content" in metadata:
                print(f"Reasoning content: {metadata['reasoning_content']}")

    except Exception as e:
        print(f"Error with minimal reasoning: {e}")

    print("\n" + "=" * 60)
    print("Testing GPT-5 with HIGH reasoning effort")
    print("=" * 60)

    try:
        model_high = ChatOpenAI(
            model="gpt-5", model_kwargs={"reasoning": {"effort": "high"}}, temperature=0
        )

        response = await model_high.ainvoke("What is 2+2? Please show your reasoning process.")
        print(f"Response: {response.content}")

        # Check if reasoning_content is available
        if hasattr(response, "response_metadata"):
            metadata = response.response_metadata
            if "reasoning_content" in metadata:
                print(f"Reasoning content: {metadata['reasoning_content']}")

    except Exception as e:
        print(f"Error with high reasoning: {e}")

    # Also test standard configuration
    print("\n" + "=" * 60)
    print("Testing GPT-5 with STANDARD configuration (no reasoning params)")
    print("=" * 60)

    try:
        model_standard = ChatOpenAI(model="gpt-5", temperature=0)

        response = await model_standard.ainvoke("What is 2+2? Please show your reasoning process.")
        print(f"Response: {response.content}")

    except Exception as e:
        print(f"Error with standard configuration: {e}")


def main():
    """Main entry point."""
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Please set it in your .env file or environment")
        return

    print("🚀 Testing GPT-5 reasoning with langchain-openai==0.3.33")
    print("Note: GPT-5 access may be limited based on your OpenAI account")
    print()

    asyncio.run(test_gpt5_reasoning())


if __name__ == "__main__":
    main()
