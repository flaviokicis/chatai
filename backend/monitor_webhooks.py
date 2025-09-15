#!/usr/bin/env python3
"""
Webhook Monitor Script

This script helps monitor incoming WhatsApp webhooks logged to /tmp/webhook-calls/

Note: Webhook logging only works in debug/development mode:
    - Set DEBUG=true in environment variables, or
    - Set ENVIRONMENT=development in your settings

Usage:
    python monitor_webhooks.py                    # Show latest 10 webhook files
    python monitor_webhooks.py --tail             # Continuously monitor for new webhooks
    python monitor_webhooks.py --sender 5522988   # Filter by sender number
    python monitor_webhooks.py --show FILE        # Show full content of a specific file
"""

import argparse
import json
import os
import time
from datetime import datetime

WEBHOOK_DIR = "/tmp/webhook-calls"


def list_webhook_files(sender_filter=None, limit=10):
    """List webhook files, optionally filtered by sender."""
    if not os.path.exists(WEBHOOK_DIR):
        print(f"❌ Webhook directory {WEBHOOK_DIR} does not exist")
        print("💡 Note: Webhook logging only works in debug/development mode")
        print("   Set DEBUG=true or ENVIRONMENT=development in your settings")
        return []

    files = []
    for filename in os.listdir(WEBHOOK_DIR):
        if filename.endswith(".txt"):
            if sender_filter and sender_filter not in filename:
                continue

            filepath = os.path.join(WEBHOOK_DIR, filename)
            stat = os.stat(filepath)
            files.append(
                {
                    "name": filename,
                    "path": filepath,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                }
            )

    # Sort by modification time (newest first)
    files.sort(key=lambda x: x["modified"], reverse=True)

    return files[:limit] if limit else files


def show_webhook_summary(files):
    """Show a summary of webhook files."""
    if not files:
        print("📭 No webhook files found")
        return

    print(f"📊 Found {len(files)} webhook files:")
    print("-" * 80)

    for file_info in files:
        # Extract sender and timestamp from filename
        parts = file_info["name"].replace(".txt", "").split("_")
        sender = parts[0] if parts else "unknown"
        timestamp_str = "_".join(parts[1:]) if len(parts) > 1 else "unknown"

        print(f"📱 Sender: {sender}")
        print(f"⏰ Time: {file_info['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📄 File: {file_info['name']}")
        print(f"📏 Size: {file_info['size']} bytes")

        # Try to show message preview
        try:
            with open(file_info["path"], encoding="utf-8") as f:
                data = json.load(f)
                if "parsed_params" in data:
                    # Try to extract message from different formats
                    message = None
                    if "Body" in data["parsed_params"]:
                        message = data["parsed_params"]["Body"]
                    elif "entry" in data["parsed_params"]:
                        try:
                            entry = data["parsed_params"]["entry"][0]
                            changes = entry.get("changes", [{}])[0]
                            messages = changes.get("value", {}).get("messages", [{}])
                            if messages:
                                message = messages[0].get("text", {}).get("body")
                        except (IndexError, KeyError):
                            pass

                    if message:
                        preview = message[:50] + "..." if len(message) > 50 else message
                        print(f"💬 Message: {preview}")
        except Exception:
            pass

        print("-" * 40)


def show_webhook_content(filename):
    """Show full content of a webhook file."""
    filepath = os.path.join(WEBHOOK_DIR, filename)

    if not os.path.exists(filepath):
        print(f"❌ File {filename} not found in {WEBHOOK_DIR}")
        return

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        print(f"📄 Full content of {filename}:")
        print("=" * 80)
        print(json.dumps(data, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"❌ Error reading file: {e}")


def monitor_webhooks():
    """Continuously monitor for new webhook files."""
    print("👀 Monitoring webhooks... (Press Ctrl+C to stop)")
    print(f"📁 Watching directory: {WEBHOOK_DIR}")

    seen_files = set()

    # Initialize with existing files
    if os.path.exists(WEBHOOK_DIR):
        seen_files = set(os.listdir(WEBHOOK_DIR))

    try:
        while True:
            if os.path.exists(WEBHOOK_DIR):
                current_files = set(os.listdir(WEBHOOK_DIR))
                new_files = current_files - seen_files

                for new_file in new_files:
                    if new_file.endswith(".txt"):
                        print(f"\n🆕 New webhook: {new_file}")

                        # Show quick preview
                        filepath = os.path.join(WEBHOOK_DIR, new_file)
                        try:
                            with open(filepath, encoding="utf-8") as f:
                                data = json.load(f)

                            timestamp = data.get("timestamp", "unknown")
                            client_ip = data.get("client_ip", "unknown")
                            method = data.get("method", "unknown")

                            print(f"   ⏰ {timestamp}")
                            print(f"   🌐 {client_ip}")
                            print(f"   📡 {method}")

                        except Exception as e:
                            print(f"   ❌ Error reading file: {e}")

                seen_files = current_files

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n👋 Monitoring stopped")


def main():
    parser = argparse.ArgumentParser(description="Monitor WhatsApp webhooks")
    parser.add_argument("--tail", action="store_true", help="Continuously monitor for new webhooks")
    parser.add_argument("--sender", help="Filter by sender number")
    parser.add_argument("--show", help="Show full content of a specific file")
    parser.add_argument("--limit", type=int, default=10, help="Limit number of files to show")

    args = parser.parse_args()

    if args.show:
        show_webhook_content(args.show)
    elif args.tail:
        monitor_webhooks()
    else:
        files = list_webhook_files(sender_filter=args.sender, limit=args.limit)
        show_webhook_summary(files)


if __name__ == "__main__":
    main()
