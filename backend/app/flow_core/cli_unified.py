#!/usr/bin/env python3
"""
Unified CLI that uses the same flow processing approach as WhatsApp.

This CLI demonstrates the flow processing architecture with:
1. Create FlowRequest-like structure
2. Process with FlowTurnRunner 
3. Display response

This matches the core flow processing used in production.
"""

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path
from queue import Queue

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from app.core.langchain_adapter import LangChainToolsLLM
from app.flow_core.compiler import compile_flow
from app.flow_core.ir import Flow
from app.flow_core.runner import FlowTurnRunner


class UnifiedCLI:
    """CLI that uses the same flow processing approach as production."""

    def __init__(self, flow_path: str, model: str = "gpt-5", no_rewrite: bool = False):
        """Initialize the CLI."""
        self.flow_path = flow_path
        self.model = model
        self.no_rewrite = no_rewrite
        self.message_queue = Queue()
        self.running = True

        # User/session identifiers (like WhatsApp phone number)
        self.user_id = f"cli:{os.getpid()}"
        self.flow_id = Path(flow_path).stem
        self.session_id = f"{self.user_id}:{self.flow_id}"

        # Core components
        self.runner = None
        self.context = None
        self.llm_client = None
        self.project_context = None

        # Threading
        self.input_thread = None
        self.shutdown_event = threading.Event()

    async def initialize(self):
        """Initialize all components."""
        print("🔧 Initializing Unified CLI...")

        # Load environment
        load_dotenv()

        # Load and compile flow
        try:
            with open(self.flow_path, encoding="utf-8") as f:
                flow_data = json.load(f)
            print(f"📁 Loaded flow: {self.flow_path}")

            flow = Flow.model_validate(flow_data)
            compiled_flow = compile_flow(flow)
            flow_name = flow.metadata.name if flow.metadata else compiled_flow.id
            print(f"✅ Compiled flow: {flow_name}")

        except Exception as e:
            print(f"❌ Failed to load/compile flow: {e}")
            return False

        # Initialize LLM
        try:
            if self.model.startswith("gpt"):
                if not os.getenv("OPENAI_API_KEY"):
                    print("❌ OPENAI_API_KEY required for GPT models")
                    return False
                chat_model = init_chat_model(self.model, model_provider="openai")
            else:
                if not os.getenv("GOOGLE_API_KEY"):
                    print("❌ GOOGLE_API_KEY required for non-OpenAI models")
                    return False
                chat_model = init_chat_model(self.model, model_provider="google")

            self.llm_client = LangChainToolsLLM(chat_model)
            print(f"🤖 LLM initialized: {self.model}")

        except Exception as e:
            print(f"❌ Failed to initialize LLM: {e}")
            return False

        # Initialize flow runner (same as production)
        self.runner = FlowTurnRunner(compiled_flow, self.llm_client)
        self.context = self.runner.initialize_context()

        # Optional: Initialize project context (like in production)
        # In production, this comes from tenant config
        self.project_context = None

        print("✅ All components initialized")
        return True

    def start_input_thread(self):
        """Start input thread for concurrent input."""
        self.input_thread = threading.Thread(target=self._input_worker, daemon=True)
        self.input_thread.start()

    def _input_worker(self):
        """Handle user input in separate thread."""
        print("\n💬 Start typing messages (type 'quit' to exit):")
        while not self.shutdown_event.is_set():
            try:
                message = input("You: ").strip()
                if message:
                    if message.lower() in ["quit", "exit", "bye"]:
                        self.shutdown_event.set()
                        break
                    self.message_queue.put({
                        "text": message,
                        "timestamp": time.time()
                    })
            except (EOFError, KeyboardInterrupt):
                self.shutdown_event.set()
                break

    async def process_message_queue(self):
        """Process messages from queue (like production flow processor)."""
        while not self.shutdown_event.is_set():
            try:
                if not self.message_queue.empty():
                    message_data = self.message_queue.get_nowait()
                    await self._process_message(message_data)

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)

            except Exception as e:
                print(f"❌ Error in message processing: {e}")
                await asyncio.sleep(1)

    async def _process_message(self, message_data: dict):
        """Process a single message using the production flow."""
        message_text = message_data["text"]
        timestamp = message_data["timestamp"]

        print(f"\n🔄 Processing: '{message_text}'")
        start_time = time.time()

        try:
            # This mirrors the production flow processing
            result = self.runner.process_turn(
                ctx=self.context,
                user_message=message_text,
                project_context=self.project_context
            )

            # Update context (like production)
            self.context = result.ctx if hasattr(result, "ctx") else self.context

            # Display response (like WhatsApp adapter would)
            await self._display_response(result)

            # Show processing stats
            processing_time = (time.time() - start_time) * 1000
            print(f"   ⏱️  Processed in {processing_time:.0f}ms")

            # Handle terminal states (like production)
            if result.terminal:
                print("\n🎉 Flow completed!")
                await self._show_final_results()
                self.shutdown_event.set()

            if result.escalate:
                print("\n🚨 Escalated to human agent")
                await self._show_final_results()
                self.shutdown_event.set()

        except Exception as e:
            print(f"❌ Error processing message: {e}")

    async def _display_response(self, result):
        """Display response like WhatsApp adapter would."""
        # Display messages (primary response format)
        if result.messages:
            for msg in result.messages:
                delay_ms = msg.get("delay_ms", 0)
                if delay_ms > 0:
                    print(f"   [delay: {delay_ms}ms]")
                    # In production, this would be handled by WhatsApp API
                    await asyncio.sleep(delay_ms / 1000.0)
                print(f"🤖 {msg['text']}")

        # Fallback to assistant message
        elif result.assistant_message:
            print(f"🤖 {result.assistant_message}")

        # Show debug information (like logs in production)
        if result.tool_name:
            print(f"   🔧 Tool: {result.tool_name}")
        if result.confidence < 1.0:
            print(f"   📊 Confidence: {result.confidence:.2f}")
        if result.reasoning:
            print(f"   🧠 Reasoning: {result.reasoning}")
        if result.answers_diff:
            print(f"   📝 Answers updated: {result.answers_diff}")

    async def _show_final_results(self):
        """Show final results like production logging would."""
        if self.context.answers:
            print("\n📋 Final collected answers:")
            for key, value in self.context.answers.items():
                print(f"  • {key}: {value}")
        else:
            print("\n📋 No answers collected")

        # Show context stats
        print("\n📊 Session stats:")
        print(f"  • Session ID: {self.session_id}")
        print(f"  • Current node: {self.context.current_node_id}")
        print(f"  • Total answers: {len(self.context.answers)}")

    async def run(self):
        """Run the unified CLI."""
        if not await self.initialize():
            return

        print("\n" + "="*60)
        print("🚀 UNIFIED CLI - Production Flow Processing")
        print("="*60)
        print("This CLI uses the exact same flow processing as WhatsApp:")
        print("  • FlowTurnRunner (same as production)")
        print("  • GPT-5 decision making")
        print("  • Context management")
        print("  • Message formatting")
        print("="*60)

        # Start input handling
        self.start_input_thread()

        try:
            # Process messages (main loop like production)
            await self.process_message_queue()

        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user")
        finally:
            self.shutdown_event.set()

        print("\n👋 Session ended")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Unified CLI - Uses production flow processing"
    )
    parser.add_argument(
        "flow_path",
        type=str,
        help="Path to the flow JSON file"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5",
        help="LLM model to use (default: gpt-5)"
    )
    parser.add_argument(
        "--no-rewrite",
        action="store_true",
        help="Disable message rewriting (raw responses)"
    )

    args = parser.parse_args()

    # Validate flow path
    if not Path(args.flow_path).exists():
        print(f"❌ Flow file not found: {args.flow_path}")
        return 1

    # Create and run CLI
    cli = UnifiedCLI(args.flow_path, args.model, args.no_rewrite)
    await cli.run()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
