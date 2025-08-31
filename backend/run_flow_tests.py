#!/usr/bin/env python3
"""Simple test runner for flow modification tools tests."""

import os
import subprocess
import sys


def run_tests():
    """Run the flow modification tools tests."""
    # Ensure we're in the backend directory
    if not os.path.exists("app"):
        print("❌ Please run this from the backend/ directory")
        sys.exit(1)

    # Set Python path
    os.environ["PYTHONPATH"] = "."

    # Run the specific test file
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/test_flow_modification_tools.py",
        "-v",  # Verbose output
        "--tb=short",  # Short traceback format
        "--no-header",  # Less clutter
        "-x",  # Stop on first failure
    ]

    print("🚀 Running flow modification tools tests...")
    print("Command:", " ".join(cmd))
    print("=" * 60)

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            print("=" * 60)
            print("✅ All tests passed!")
        else:
            print("=" * 60)
            print("❌ Some tests failed!")
        return result.returncode
    except KeyboardInterrupt:
        print("\n⚠️ Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1

if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
