#!/usr/bin/env python3
"""
Async CLI for testing flows with non-blocking input.

This CLI allows you to type messages while waiting for responses,
simulating rapid message scenarios like WhatsApp.
"""

import asyncio
import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import threading
from queue import Queue
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.flow_core.compiler import compile_flow
from app.flow_core.ir import Flow
from app.core.flow_processor import FlowProcessor, FlowRequest, FlowProcessingResult
from app.core.channel_adapter import ConversationalRewriter, CLIAdapter
from app.core.langchain_adapter import LangChainToolsLLM
from app.services.session_manager import RedisSessionManager
from app.core.state import ConversationStore
from langchain.chat_models import init_chat_model
import redis


class AsyncFlowCLI:
    """Async CLI that allows typing while processing."""
    
    def __init__(self, flow_path: str, model: str = "gpt-4o", no_rewrite: bool = False):
        """Initialize the async CLI."""
        self.flow_path = flow_path
        self.model = model
        self.no_rewrite = no_rewrite
        self.message_queue = Queue()
        self.response_queue = Queue()
        self.processing = False
        self.flow_processor = None
        self.flow_dict = None
        self.llm_client = None
        self.rewriter = None
        self.user_id = f"cli_user_{os.getpid()}"
        self.flow_id = "cli_flow"
        
    def setup(self):
        """Setup the flow and LLM."""
        # Load and compile flow
        with open(self.flow_path, 'r') as f:
            flow_dict = json.load(f)
        
        flow = Flow.model_validate(flow_dict)
        compiled = compile_flow(flow)
        
        # Setup LLM
        if self.model.startswith("gpt"):
            provider = "openai"
            if not os.environ.get("OPENAI_API_KEY"):
                print("[error] OPENAI_API_KEY not set")
                sys.exit(1)
        else:
            provider = "google_genai"
            if not os.environ.get("GOOGLE_API_KEY"):
                print("[error] GOOGLE_API_KEY not set")
                sys.exit(1)
        
        chat = init_chat_model(self.model, model_provider=provider)
        llm_client = LangChainToolsLLM(chat)
        
        # Initialize runner and context
        self.runner = FlowTurnRunner(compiled, llm_client, strict_mode=False)
        self.ctx = self.runner.initialize_context()
        
        # Setup rewriter
        self.rewriter = ConversationalRewriter(llm_client if not self.no_rewrite else None)
        
        print(f"[mode] Async CLI: model={self.model}, rewrite={'off' if self.no_rewrite else 'on'}")
        print("[info] Type messages anytime - they'll be aggregated if sent rapidly")
        print("[info] Type 'exit' or Ctrl+C to quit\n")
        
    def input_thread(self):
        """Thread to handle non-blocking input."""
        while True:
            try:
                message = input()
                if message.lower() in ['exit', 'quit', 'q']:
                    self.message_queue.put(None)
                    break
                if message.strip():
                    self.message_queue.put(message)
            except (EOFError, KeyboardInterrupt):
                self.message_queue.put(None)
                break
    
    async def process_messages(self):
        """Process messages with cancellation support."""
        pending_messages = []
        last_message_time = 0
        wait_time = 1.5  # Wait 1.5 seconds after last message before processing
        
        while True:
            # Check for new messages
            has_new_message = False
            while not self.message_queue.empty():
                msg = self.message_queue.get()
                if msg is None:  # Exit signal
                    return
                pending_messages.append(msg)
                last_message_time = time.time()
                has_new_message = True
                print(f"[buffered] {msg}")
                
            current_time = time.time()
            time_since_last = current_time - last_message_time
            
            # If we have pending messages and enough time has passed since last message
            if pending_messages and time_since_last > wait_time:
                # Check if we should cancel ongoing processing
                if self.processing:
                    print(f"[system] Cancelling previous processing...")
                    # In a real implementation, we'd cancel the actual processing
                    # For now, just mark that we want to cancel
                    self.processing = False
                    await asyncio.sleep(0.5)  # Wait for processing to stop
                
                # Aggregate and process all pending messages
                combined = " ".join(pending_messages)
                print(f"[system] Processing aggregated message: {combined[:100]}...")
                pending_messages = []
                await self.process_single_message(combined)
            
            # Small delay to prevent busy waiting
            await asyncio.sleep(0.1)
    
    async def process_single_message(self, message: str):
        """Process a single (possibly aggregated) message."""
        self.processing = True
        token = self.cancellation_manager.create_cancellation_token(self.session_id)
        
        try:
            print(f"\n[you] {message}")
            
            # Check for cancellation before processing
            if token.is_set():
                print("[system] Processing cancelled")
                return
            
            # Process through flow
            result = self.runner.process_turn(self.ctx, message)
            
            # Check for cancellation before displaying
            if token.is_set():
                print("[system] Processing cancelled before response")
                return
            
            # Display response
            if result.assistant_message:
                # Get project context for rewriting
                project_context = None
                if hasattr(self.ctx, 'project_context'):
                    project_context = self.ctx.project_context
                
                # Build chat history
                chat_history = self.rewriter.build_chat_history(
                    flow_context_history=getattr(self.ctx, "history", None)
                )
                
                # Rewrite if enabled
                if not self.no_rewrite:
                    messages = self.rewriter.rewrite_message(
                        result.assistant_message,
                        chat_history,
                        enable_rewrite=True,
                        project_context=project_context,
                        current_time=datetime.now().strftime("%H:%M")
                    )
                    
                    for msg in messages:
                        text = msg.get("text", "")
                        if text:
                            print(f"[assistant] {text}")
                            if len(messages) > 1:
                                await asyncio.sleep(0.5)  # Brief delay between messages
                else:
                    print(f"[assistant] {result.assistant_message}")
            
            # Check terminal conditions
            if result.terminal:
                print("\n[system] Flow completed")
                return
                
        except Exception as e:
            print(f"[error] {e}")
        finally:
            self.processing = False
            self.cancellation_manager.mark_processing_complete(self.session_id)
    
    async def run(self):
        """Run the async CLI."""
        self.setup()
        
        # Show initial prompt if any
        result = self.runner.process_turn(self.ctx, None)
        if result.assistant_message:
            print(f"[assistant] {result.assistant_message}\n")
        
        # Start input thread
        input_thread = threading.Thread(target=self.input_thread, daemon=True)
        input_thread.start()
        
        # Process messages
        try:
            await self.process_messages()
        except KeyboardInterrupt:
            print("\n[system] Exiting...")
        
        print("\n[system] Goodbye!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Async Flow CLI - Type while processing!")
    parser.add_argument("flow", help="Path to flow JSON file")
    parser.add_argument("--model", default="gpt-4o", help="LLM model to use")
    parser.add_argument("--no-rewrite", action="store_true", help="Disable message rewriting")
    
    args = parser.parse_args()
    
    if not Path(args.flow).exists():
        print(f"[error] Flow file not found: {args.flow}")
        sys.exit(1)
    
    cli = AsyncFlowCLI(args.flow, args.model, args.no_rewrite)
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()
