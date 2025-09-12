#!/usr/bin/env python3
"""
Async CLI for testing flows with non-blocking input.

This CLI allows you to type messages while waiting for responses,
simulating rapid message scenarios like WhatsApp.
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


class AsyncFlowCLI:
    """Async CLI that allows typing while processing."""

    def __init__(self, flow_path: str, model: str = "gpt-5", no_rewrite: bool = False):
        """Initialize the async CLI."""
        self.flow_path = flow_path
        self.model = model
        self.no_rewrite = no_rewrite
        self.message_queue = Queue()
        self.response_queue = Queue()
        self.processing = False
        self.runner = None
        self.context = None
        self.flow_dict = None
        self.llm_client = None
        self.user_id = f"cli_user_{os.getpid()}"

        # Threading control
        self.shutdown_event = threading.Event()
        self.input_thread = None
        self.processing_task = None

    async def initialize(self):
        """Initialize the flow and LLM."""
        # Load environment variables
        load_dotenv()

        # Load flow
        try:
            with open(self.flow_path, encoding="utf-8") as f:
                self.flow_dict = json.load(f)
            print(f"📁 Loaded flow from: {self.flow_path}")
        except Exception as e:
            print(f"❌ Failed to load flow: {e}")
            return False

        # Compile flow
        try:
            flow = Flow.model_validate(self.flow_dict)
            compiled_flow = compile_flow(flow)
            flow_name = flow.metadata.name if flow.metadata else compiled_flow.id
            print(f"✅ Flow compiled: {flow_name}")
        except Exception as e:
            print(f"❌ Failed to compile flow: {e}")
            return False

        # Initialize LLM
        try:
            if self.model.startswith("gpt"):
                if not os.getenv("OPENAI_API_KEY"):
                    print("❌ OPENAI_API_KEY environment variable required for GPT models")
                    return False
                chat_model = init_chat_model(self.model, model_provider="openai")
            else:
                if not os.getenv("GOOGLE_API_KEY"):
                    print("❌ GOOGLE_API_KEY environment variable required for non-OpenAI models")
                    return False
                chat_model = init_chat_model(self.model, model_provider="google")

            self.llm_client = LangChainToolsLLM(chat_model)
            print(f"🤖 LLM initialized: {self.model}")
        except Exception as e:
            print(f"❌ Failed to initialize LLM: {e}")
            return False

        # Initialize runner and context
        self.runner = FlowTurnRunner(compiled_flow, self.llm_client)
        self.context = self.runner.initialize_context()

        return True

    def start_input_thread(self):
        """Start the input thread for non-blocking input."""
        self.input_thread = threading.Thread(target=self._input_worker, daemon=True)
        self.input_thread.start()

    def _input_worker(self):
        """Worker thread for handling user input."""
        print("🎯 Type messages (type 'quit' to exit):")
        while not self.shutdown_event.is_set():
            try:
                user_input = input("You: ").strip()
                if user_input:
                    if user_input.lower() in ["quit", "exit", "bye"]:
                        self.shutdown_event.set()
                        break
                    self.message_queue.put(user_input)
            except (EOFError, KeyboardInterrupt):
                self.shutdown_event.set()
                break

    async def process_messages(self):
        """Process messages from the queue."""
        while not self.shutdown_event.is_set():
            try:
                # Check for new messages (non-blocking)
                if not self.message_queue.empty() and not self.processing:
                    message = self.message_queue.get_nowait()
                    await self._process_single_message(message)

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)

            except Exception as e:
                print(f"❌ Error in message processing: {e}")
                await asyncio.sleep(1)

    async def _process_single_message(self, message: str):
        """Process a single message."""
        if self.processing:
            print("⏳ Already processing, queuing message...")
            return

        self.processing = True
        start_time = time.time()

        try:
            print(f"🔄 Processing: '{message}'")

            # Process the turn
            result = self.runner.process_turn(self.context, message)

            # Update context
            self.context = result.ctx if hasattr(result, "ctx") else self.context

            # Display response
            if result.messages:
                for msg in result.messages:
                    delay_ms = msg.get("delay_ms", 0)
                    if delay_ms > 0:
                        print(f"   [delay: {delay_ms}ms]")
                    print(f"🤖 {msg['text']}")
            elif result.assistant_message:
                print(f"🤖 {result.assistant_message}")

            # Show debug info
            processing_time = (time.time() - start_time) * 1000
            print(f"   [Processed in {processing_time:.0f}ms]")

            if result.tool_name:
                print(f"   [Tool: {result.tool_name}]")
            if result.confidence < 1.0:
                print(f"   [Confidence: {result.confidence:.2f}]")
            if result.reasoning:
                print(f"   [Reasoning: {result.reasoning}]")

            # Check for completion
            if result.terminal:
                print("🎉 Flow completed!")
                if self.context.answers:
                    print("\n📋 Final answers:")
                    for key, value in self.context.answers.items():
                        print(f"  {key}: {value}")
                self.shutdown_event.set()

            # Check for escalation
            if result.escalate:
                print("🚨 Escalated to human agent")
                self.shutdown_event.set()

        except Exception as e:
            print(f"❌ Error processing message: {e}")
        finally:
            self.processing = False

    async def run(self):
        """Run the async CLI."""
        if not await self.initialize():
            return

        print("\n" + "="*50)
        print("🚀 ASYNC FLOW CLI STARTED")
        print("="*50)
        print("Features:")
        print("  • Type messages while processing")
        print("  • Real-time response display")
        print("  • Non-blocking input")
        print("="*50)
        print()

        # Start input thread
        self.start_input_thread()

        # Start message processing
        try:
            await self.process_messages()
        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user")
        finally:
            self.shutdown_event.set()

        print("\n👋 Session ended")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Async Flow CLI - Non-blocking flow testing")
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
        return

    # Create and run CLI
    cli = AsyncFlowCLI(args.flow_path, args.model, args.no_rewrite)
    await cli.run()


if __name__ == "__main__":
    asyncio.run(main())
