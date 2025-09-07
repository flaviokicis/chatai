#!/usr/bin/env python3
"""
Unified CLI that uses the exact same flow processor as WhatsApp.

This CLI demonstrates how thin the channel layer should be - just:
1. Create FlowRequest
2. Call FlowProcessor
3. Display response

Everything else (cancellation, aggregation, etc.) is handled by the core.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional
import argparse
import threading
from queue import Queue
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.flow_processor import FlowProcessor, FlowRequest, FlowProcessingResult
from app.core.channel_adapter import ConversationalRewriter
from app.core.langchain_adapter import LangChainToolsLLM
from app.core.state import ConversationStore
from app.services.session_manager import RedisSessionManager
from app.core.app_context import AppContext
from langchain.chat_models import init_chat_model
import redis


class UnifiedCLI:
    """CLI that uses the exact same flow processor as WhatsApp."""
    
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
        
        # Flow definition (loaded once)
        with open(flow_path, 'r') as f:
            self.flow_definition = json.load(f)
        
        # These will be initialized in setup()
        self.flow_processor = None
        self.app_context = None
        self.rewriter = None
        
    def setup(self):
        """Setup dependencies exactly like WhatsApp does."""
        # Setup LLM (same as WhatsApp)
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
        llm = LangChainToolsLLM(chat)
        
        # Setup Redis store (required for cancellation/aggregation)
        try:
            redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                db=int(os.getenv("REDIS_DB", 0)),
                decode_responses=True
            )
            redis_client.ping()
            print(f"[info] Connected to Redis at {redis_client.connection_pool.connection_kwargs['host']}:{redis_client.connection_pool.connection_kwargs['port']}")
        except:
            print("[warning] Redis not available - using in-memory store (no cancellation/aggregation)")
            redis_client = None
        
        # Create store and session manager
        store = ConversationStore(redis_client=redis_client) if redis_client else None
        session_manager = RedisSessionManager(store) if store else None
        
        # Create app context (like WhatsApp)
        self.app_context = AppContext(
            llm=llm,
            store=store,
            request=None  # CLI doesn't have HTTP request
        )
        
        # Create flow processor (exact same as WhatsApp)
        self.flow_processor = FlowProcessor(
            llm=llm,
            session_manager=session_manager,
            training_handler=None,
            thread_updater=None  # CLI doesn't update threads
        )
        
        # Setup rewriter
        self.rewriter = ConversationalRewriter(llm if not self.no_rewrite else None)
        
        print(f"[mode] Unified CLI: model={self.model}, rewrite={'off' if self.no_rewrite else 'on'}")
        print("[info] Using same FlowProcessor as WhatsApp - with cancellation/aggregation")
        print("[info] Type messages rapidly to test aggregation")
        print("[info] Type 'exit' to quit\n")
    
    def input_thread(self):
        """Thread for non-blocking input."""
        while self.running:
            try:
                message = input()
                if message.lower() in ['exit', 'quit', 'q']:
                    self.running = False
                    break
                if message.strip():
                    self.message_queue.put(message)
            except (EOFError, KeyboardInterrupt):
                self.running = False
                break
    
    async def process_messages(self):
        """Process messages through the flow processor."""
        # Show initial prompt
        initial_response = await self._process_message(None)
        if initial_response and initial_response.message:
            self._display_response(initial_response.message)
        
        while self.running:
            # Collect messages (simulate rapid typing)
            messages = []
            deadline = None
            
            # Keep collecting messages for a short window
            while True:
                try:
                    # Non-blocking check for messages
                    if not self.message_queue.empty():
                        msg = self.message_queue.get_nowait()
                        messages.append(msg)
                        # Reset deadline when new message arrives
                        deadline = time.time() + 0.5  # 500ms after last message
                        print(f"[buffered] {msg}")
                    
                    # If we have messages and deadline passed, process them
                    if messages and deadline and time.time() > deadline:
                        break
                    
                    # Small sleep to prevent busy waiting
                    await asyncio.sleep(0.05)
                    
                    # Check if we should exit
                    if not self.running:
                        return
                        
                except:
                    break
            
            # Process aggregated messages (or single message)
            if messages:
                combined = " ".join(messages)
                print(f"\n[you] {combined}")
                
                # Process through flow processor (exact same as WhatsApp)
                response = await self._process_message(combined)
                
                if response:
                    if response.result == FlowProcessingResult.TERMINAL:
                        print("\n[system] Flow completed")
                        self.running = False
                        break
                    elif response.result == FlowProcessingResult.ESCALATE:
                        print("\n[system] Flow escalated to human")
                        self.running = False
                        break
                    elif response.message:
                        self._display_response(response.message)
    
    async def _process_message(self, message: Optional[str]):
        """Process a message exactly like WhatsApp does."""
        # Create flow request (same structure as WhatsApp)
        flow_request = FlowRequest(
            user_id=self.user_id,
            user_message=message,
            flow_definition=self.flow_definition,
            flow_metadata={
                "flow_name": self.flow_id,
                "flow_id": self.flow_id,
                "thread_id": None,  # CLI doesn't have threads
                "selected_flow_id": self.flow_id,
            },
            tenant_id=None,  # CLI doesn't have tenants
            project_context=None,  # Could add if needed
            channel_id="cli"
        )
        
        # Process through flow processor (exact same call as WhatsApp)
        try:
            return await self.flow_processor.process_flow(flow_request, self.app_context)
        except Exception as e:
            print(f"[error] {e}")
            return None
    
    def _display_response(self, message: str):
        """Display response with optional rewriting."""
        if self.no_rewrite:
            print(f"[assistant] {message}")
        else:
            # Rewrite like WhatsApp does
            try:
                messages = self.rewriter.rewrite_message(
                    message,
                    [],  # Could add history if needed
                    enable_rewrite=True,
                    project_context=None,
                    is_completion=False,
                    tool_context=None,
                    current_time=time.strftime("%H:%M")
                )
                
                for msg in messages:
                    if msg.get("text"):
                        print(f"[assistant] {msg['text']}")
                        if len(messages) > 1:
                            time.sleep(0.5)  # Brief delay between messages
            except:
                # Fallback to raw message
                print(f"[assistant] {message}")
    
    async def run(self):
        """Run the CLI."""
        self.setup()
        
        # Start input thread
        input_thread = threading.Thread(target=self.input_thread, daemon=True)
        input_thread.start()
        
        # Process messages
        try:
            await self.process_messages()
        except KeyboardInterrupt:
            print("\n[system] Interrupted")
        
        self.running = False
        print("\n[system] Goodbye!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Unified Flow CLI - Uses exact same processor as WhatsApp"
    )
    parser.add_argument("flow", help="Path to flow JSON file")
    parser.add_argument("--model", default="gpt-5", help="LLM model to use")
    parser.add_argument("--no-rewrite", action="store_true", help="Disable message rewriting")
    
    args = parser.parse_args()
    
    if not Path(args.flow).exists():
        print(f"[error] Flow file not found: {args.flow}")
        sys.exit(1)
    
    cli = UnifiedCLI(args.flow, args.model, args.no_rewrite)
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()

