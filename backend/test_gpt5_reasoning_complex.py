#!/usr/bin/env python3
"""Test GPT-5 with a complex reasoning problem that should show clear differences."""

import asyncio
import os
import time
from typing import Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Load environment variables
load_dotenv()


async def test_reasoning_with_complex_problem(
    effort: Literal["minimal", "medium", "high"], prompt: str
) -> tuple[str, float, str]:
    """Test a single reasoning level with detailed output."""

    model = ChatOpenAI(model="gpt-5", model_kwargs={"reasoning": {"effort": effort}}, temperature=0)

    print(f"\n{'=' * 70}")
    print(f"Testing {effort.upper()} reasoning effort...")
    print(f"{'=' * 70}")

    start_time = time.perf_counter()
    try:
        response = await model.ainvoke(prompt)
        end_time = time.perf_counter()
        latency = end_time - start_time

        # Extract content from response
        content = str(response.content)
        if isinstance(response.content, list) and len(response.content) > 0:
            if isinstance(response.content[0], dict) and "text" in response.content[0]:
                content = response.content[0]["text"]

        print(f"⏱️  Latency: {latency:.2f} seconds")
        print(f"\n📝 Full Response ({len(content)} chars):")
        print("-" * 70)
        print(content)
        print("-" * 70)

        return effort, latency, content
    except Exception as e:
        end_time = time.perf_counter()
        latency = end_time - start_time
        print(f"❌ Error: {e!s}")
        return effort, latency, f"Error: {e!s}"


async def main():
    """Run tests with complex reasoning problems."""

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        return

    # Complex logical reasoning problem
    logic_prompt = """Solve this logic puzzle step by step:

    Three friends (Alice, Bob, and Charlie) each have a different pet (dog, cat, bird) 
    and live in different colored houses (red, blue, green).

    Clues:
    1. Alice doesn't live in the red house
    2. The person with the dog lives in the blue house
    3. Charlie doesn't have a cat
    4. Bob doesn't live in the green house
    5. The person in the red house doesn't have a bird

    Determine who lives where and what pet each person has. 
    Show your reasoning process step by step."""

    # Complex math problem
    math_prompt = """Solve this problem step by step with detailed reasoning:

    A bacteria culture doubles every 3 hours. If you start with 100 bacteria at 9:00 AM:
    1. How many bacteria will there be at 6:00 PM the same day?
    2. At what time will the culture first exceed 10,000 bacteria?
    3. If the maximum capacity is 1 million bacteria, when will this be reached?
    
    Show all calculations and explain your reasoning for each step."""

    print("\n" + "=" * 70)
    print("GPT-5 REASONING EFFORT COMPARISON - COMPLEX PROBLEMS")
    print("=" * 70)

    # Test 1: Logic puzzle
    print("\n🧩 TEST 1: LOGIC PUZZLE")
    print("-" * 70)
    print(logic_prompt)

    print("\nRunning all three reasoning levels in parallel...")

    start_total = time.perf_counter()
    logic_results = await asyncio.gather(
        test_reasoning_with_complex_problem("minimal", logic_prompt),
        test_reasoning_with_complex_problem("medium", logic_prompt),
        test_reasoning_with_complex_problem("high", logic_prompt),
    )
    total_time = time.perf_counter() - start_total

    print(f"\n⏱️  Total parallel execution time: {total_time:.2f}s")

    # Analyze results
    print("\n" + "=" * 70)
    print("📊 LOGIC PUZZLE - LATENCY COMPARISON:")
    print("-" * 70)

    for effort, latency, _ in logic_results:
        print(f"• {effort.capitalize():8s} effort: {latency:6.2f} seconds")

    # Calculate ratios
    minimal_lat = logic_results[0][1]
    medium_lat = logic_results[1][1]
    high_lat = logic_results[2][1]

    print("\n📈 Relative Performance:")
    print(f"• Medium is {(medium_lat / minimal_lat):.1f}x slower than Minimal")
    print(f"• High is {(high_lat / minimal_lat):.1f}x slower than Minimal")

    # Test 2: Math problem
    print("\n\n🔢 TEST 2: MATH PROBLEM")
    print("-" * 70)
    print(math_prompt)

    print("\nRunning all three reasoning levels in parallel...")

    start_total = time.perf_counter()
    math_results = await asyncio.gather(
        test_reasoning_with_complex_problem("minimal", math_prompt),
        test_reasoning_with_complex_problem("medium", math_prompt),
        test_reasoning_with_complex_problem("high", math_prompt),
    )
    total_time = time.perf_counter() - start_total

    print(f"\n⏱️  Total parallel execution time: {total_time:.2f}s")

    # Analyze results
    print("\n" + "=" * 70)
    print("📊 MATH PROBLEM - LATENCY COMPARISON:")
    print("-" * 70)

    for effort, latency, _ in math_results:
        print(f"• {effort.capitalize():8s} effort: {latency:6.2f} seconds")

    # Calculate ratios
    minimal_lat = math_results[0][1]
    medium_lat = math_results[1][1]
    high_lat = math_results[2][1]

    print("\n📈 Relative Performance:")
    print(f"• Medium is {(medium_lat / minimal_lat):.1f}x slower than Minimal")
    print(f"• High is {(high_lat / minimal_lat):.1f}x slower than Minimal")

    print("\n" + "=" * 70)
    print("✅ All tests completed!")
    print("\n💡 EXPECTED: Higher reasoning effort should take longer but provide")
    print("   more detailed/accurate reasoning steps.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

