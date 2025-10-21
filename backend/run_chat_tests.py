#!/usr/bin/env python3
"""
Test runner for flow chat functionality tests.
"""

import subprocess
import sys


def run_tests():
    """Run all flow chat related tests."""
    test_files = [
        "tests/test_flow_chat_response_structure.py",
        "tests/test_flow_chat_agent.py",
        "tests/test_enhanced_flow_chat_agent.py",
        "tests/test_flow_modification_tools.py",
    ]

    print("🧪 Running Flow Chat Tests...")
    print("=" * 50)

    for test_file in test_files:
        print(f"\n📝 Running {test_file}...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
                check=False,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                print(f"✅ {test_file} - PASSED")
            else:
                print(f"❌ {test_file} - FAILED")
                print(result.stdout)
                print(result.stderr)
        except Exception as e:
            print(f"💥 Error running {test_file}: {e}")

    print("\n" + "=" * 50)
    print("🏁 Flow chat tests complete!")


if __name__ == "__main__":
    run_tests()
