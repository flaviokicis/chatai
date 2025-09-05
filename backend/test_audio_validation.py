#!/usr/bin/env python3
"""Test audio validation with a local audio file."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.audio_validation_service import AudioValidationService


def test_audio_file(filename: str):
    """Test audio validation with a local file."""
    print("\n=== Testing Audio Validation ===")
    print(f"File: {filename}")

    if not os.path.exists(filename):
        print(f"ERROR: File not found: {filename}")
        return

    file_size = os.path.getsize(filename)
    print(f"File size: {file_size:,} bytes ({file_size/1024:.1f} KB)")

    # Read the file
    with open(filename, "rb") as f:
        audio_bytes = f.read()

    # Test validation with 5 minute limit (300 seconds)
    validator = AudioValidationService(max_duration_seconds=300)

    print(f"\nValidating with {validator.max_duration_seconds}s ({validator.max_duration_seconds/60:.0f} min) limit...")
    is_valid, duration, error_msg = validator.validate_audio_duration(audio_bytes)

    print("\nResults:")
    print(f"  Valid: {is_valid}")
    print(f"  Duration: {duration:.1f}s ({duration/60:.1f} min)" if duration else "  Duration: Could not determine")
    print(f"  Error: {error_msg}" if error_msg else "  Error: None")

    if duration:
        print("\nDuration details:")
        print(f"  Total seconds: {duration:.1f}")
        print(f"  Minutes: {duration/60:.1f}")
        print(f"  Limit: {validator.max_duration_seconds}s ({validator.max_duration_seconds/60:.0f} min)")
        print(f"  Over limit by: {(duration - validator.max_duration_seconds):.1f}s" if duration > validator.max_duration_seconds else "  Within limit ✓")

if __name__ == "__main__":
    audio_file = "WhatsApp Audio 2025-09-04 at 01.18.37.opus"
    test_audio_file(audio_file)
