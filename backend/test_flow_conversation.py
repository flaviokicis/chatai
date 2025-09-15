#!/usr/bin/env python
"""Test script for flow conversation with gas station scenario."""

import subprocess
import sys
import time


def run_conversation():
    """Run the conversation test."""
    # Start the CLI process
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.flow_core.cli",
            "--llm",
            "--model",
            "gpt-5",
            "--tenant",
            "068b37cd-c090-710d-b0b6-5ca37c2887ff",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=0,
    )

    # Conversation sequence
    conversation = [
        ("Ola", 3),
        ("Eu preciso de uma quadra", 3),
        ("Na verdade é um posto, voces vendem LED?", 5),
    ]

    output_lines = []

    try:
        for message, wait_time in conversation:
            print(f"\n>>> Sending: {message}")
            proc.stdin.write(message + "\n")
            proc.stdin.flush()
            time.sleep(wait_time)

        # Give final time for last response
        time.sleep(2)

        # Send exit
        proc.stdin.write("exit\n")
        proc.stdin.flush()
        time.sleep(1)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        proc.terminate()
        try:
            output, _ = proc.communicate(timeout=2)
            output_lines = output.split("\n")
        except:
            pass

    # Print relevant output
    print("\n" + "=" * 60)
    print("CONVERSATION OUTPUT:")
    print("=" * 60)

    for line in output_lines:
        # Filter for assistant messages and state changes
        if any(
            marker in line
            for marker in ["🤖", "Node:", "nome", "email", "altura", "marquise", "ilhas"]
        ):
            print(line)


if __name__ == "__main__":
    print("Running flow conversation test...")
    print("This will test: Greeting -> Quadra -> Correction to Gas Station")
    run_conversation()
