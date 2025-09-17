#!/usr/bin/env python3
"""Compare latency of GPT-5 with different reasoning effort levels."""

import asyncio
import os
import statistics
import time
from typing import Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Load environment variables
load_dotenv()


async def measure_reasoning_latency(
    effort: Literal["minimal", "medium", "high"], prompt: str
) -> tuple[str, float, str]:
    """Measure latency for a single reasoning effort level."""

    model = ChatOpenAI(model="gpt-5", model_kwargs={"reasoning": {"effort": effort}}, temperature=0)

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

        return effort, latency, content  # Return full response
    except Exception as e:
        end_time = time.perf_counter()
        latency = end_time - start_time
        return effort, latency, f"Error: {e!s}"


async def run_parallel_comparison():
    """Run all three reasoning levels in parallel and compare latencies."""

    # Test prompt - something that requires complex reasoning
    prompt = """A farmer needs to transport a fox, a chicken, and a bag of grain across a river. 
    The boat can only carry the farmer and one item at a time. If left alone:
    - The fox will eat the chicken
    - The chicken will eat the grain
    
    How can the farmer transport everything safely? List each step and explain why it's safe."""

    print("=" * 70)
    print("GPT-5 REASONING EFFORT LATENCY COMPARISON")
    print("=" * 70)
    print(f"\nPrompt: {prompt}\n")
    print("Starting parallel requests...")
    print("-" * 70)

    # Run all three in parallel
    start_total = time.perf_counter()
    results = await asyncio.gather(
        measure_reasoning_latency("minimal", prompt),
        measure_reasoning_latency("medium", prompt),
        measure_reasoning_latency("high", prompt),
    )
    total_time = time.perf_counter() - start_total

    # Sort results by effort level for consistent display
    effort_order = {"minimal": 1, "medium": 2, "high": 3}
    results = sorted(results, key=lambda x: effort_order[x[0]])

    # Display results
    print("\n📊 RESULTS (ran in parallel):")
    print("-" * 70)

    latencies = []
    for effort, latency, response in results:
        latencies.append(latency)
        print(f"\n🔹 Reasoning Effort: {effort.upper()}")
        print(f"   ⏱️  Latency: {latency:.2f} seconds")
        print("   📝 Full Response:")
        print(f"   {'-' * 60}")
        # Indent the response for readability
        for line in response.split("\n"):
            print(f"   {line}")
        print(f"   {'-' * 60}")
        print(f"   Response length: {len(response)} characters")

    print("\n" + "=" * 70)
    print("📈 LATENCY ANALYSIS:")
    print("-" * 70)

    # Calculate differences
    minimal_lat = results[0][1]
    medium_lat = results[1][1]
    high_lat = results[2][1]

    print(f"• Minimal effort:  {minimal_lat:.2f}s (baseline)")
    print(
        f"• Medium effort:   {medium_lat:.2f}s (+{(medium_lat - minimal_lat):.2f}s, {(medium_lat / minimal_lat):.1f}x slower)"
    )
    print(
        f"• High effort:     {high_lat:.2f}s (+{(high_lat - minimal_lat):.2f}s, {(high_lat / minimal_lat):.1f}x slower)"
    )

    print(f"\n• Total parallel execution time: {total_time:.2f}s")
    print(f"• Average latency: {statistics.mean(latencies):.2f}s")
    print(f"• Latency range: {min(latencies):.2f}s - {max(latencies):.2f}s")

    # Show percentage differences
    print("\n📊 RELATIVE PERFORMANCE:")
    print("-" * 70)
    print(f"• Medium vs Minimal: {((medium_lat - minimal_lat) / minimal_lat * 100):.1f}% slower")
    print(f"• High vs Minimal:   {((high_lat - minimal_lat) / minimal_lat * 100):.1f}% slower")
    print(f"• High vs Medium:    {((high_lat - medium_lat) / medium_lat * 100):.1f}% slower")

    print("\n" + "=" * 70)
    print("✅ Test completed successfully!")
    print("\n💡 EXPECTED BEHAVIOR:")
    print("   - Minimal effort should be fastest (optimized for speed)")
    print("   - Medium effort should be moderately slower")
    print("   - High effort should be slowest (optimized for quality)")
    print("=" * 70)


async def run_multiple_tests(num_runs: int = 3):
    """Run multiple tests to get average latencies."""

    print(f"\n🔄 Running {num_runs} rounds of tests for more accurate measurements...\n")

    all_results = {"minimal": [], "medium": [], "high": []}
    prompt = "What is 15 * 7? Show your work."

    for round_num in range(num_runs):
        print(f"Round {round_num + 1}/{num_runs}...")

        results = await asyncio.gather(
            measure_reasoning_latency("minimal", prompt),
            measure_reasoning_latency("medium", prompt),
            measure_reasoning_latency("high", prompt),
        )

        for effort, latency, _ in results:
            all_results[effort].append(latency)

    print("\n" + "=" * 70)
    print("📊 AVERAGE LATENCIES OVER MULTIPLE RUNS:")
    print("-" * 70)

    avg_minimal = statistics.mean(all_results["minimal"])
    avg_medium = statistics.mean(all_results["medium"])
    avg_high = statistics.mean(all_results["high"])

    print(f"• Minimal: {avg_minimal:.2f}s (±{statistics.stdev(all_results['minimal']):.2f}s)")
    print(f"• Medium:  {avg_medium:.2f}s (±{statistics.stdev(all_results['medium']):.2f}s)")
    print(f"• High:    {avg_high:.2f}s (±{statistics.stdev(all_results['high']):.2f}s)")

    print("\n📈 CONSISTENT DIFFERENCES:")
    print(f"• Medium is ~{(avg_medium / avg_minimal):.1f}x slower than Minimal")
    print(f"• High is ~{(avg_high / avg_minimal):.1f}x slower than Minimal")
    print("=" * 70)


async def main():
    """Main function to run all tests."""
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        return

    # Run single parallel comparison
    await run_parallel_comparison()

    # Optionally run multiple rounds for averages
    print("\n" + "=" * 70)
    print("Would you like to see averaged results over multiple runs?")
    print("(Commenting out for automated testing, uncomment if needed)")
    print("=" * 70)
    # await run_multiple_tests(3)


if __name__ == "__main__":
    asyncio.run(main())
