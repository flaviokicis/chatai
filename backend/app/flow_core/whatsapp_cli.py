#!/usr/bin/env python3
"""
WhatsApp Simulator CLI

This CLI simulates WhatsApp messaging by using the same infrastructure as the production webhook:
- Database persistence (tenants, channels, flows, threads, messages)
- Redis session management for chat history
- FlowProcessor service layer (same as webhook uses)
- Async message queue for WhatsApp-like behavior
- Proper tenant and channel context

The key: We use FlowProcessor directly (like the webhook ultimately does) with proper DB/Redis setup.
"""

# Standard library imports first (before path manipulation)
import argparse
import asyncio
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from typing import Any
from uuid import UUID, uuid4

# Add backend directory to path (but after standard imports to avoid conflicts)
backend_dir = Path(__file__).parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from redis import Redis
from sqlalchemy.orm import Session

from app.core.app_context import AppContext
from app.core.flow_processor import FlowProcessor
from app.core.flow_request import FlowRequest
from app.core.flow_response import FlowProcessingResult, FlowResponse
from app.core.langchain_adapter import LangChainToolsLLM
from app.db.models import (
    ChannelInstance,
    ChannelType,
    Flow,
    MessageDirection,
    MessageStatus,
    Tenant,
)
from app.db.repository import (
    create_message,
    find_channel_instance_by_identifier,
    get_or_create_contact,
    get_or_create_thread,
)
from app.db.session import db_session
from app.services.processing_cancellation_manager import ProcessingCancellationManager
from app.services.session_manager import RedisSessionManager
from app.services.tenant_config_service import TenantConfigService
from app.settings import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Context for a WhatsApp conversation."""

    tenant_id: UUID
    channel_id: UUID
    flow_id: UUID
    thread_id: UUID
    contact_id: UUID
    flow_definition: dict[str, Any]
    flow_metadata: dict[str, Any]
    project_context: Any
    user_phone: str
    bot_phone: str


class WhatsAppSimulatorCLI:
    """
    WhatsApp simulator that uses production infrastructure.

    This simulates WhatsApp by:
    1. Setting up DB with tenant/channel/flow like production
    2. Using FlowProcessor service (not direct FlowTurnRunner)
    3. Persisting messages to database
    4. Using Redis for session management
    5. Supporting async messaging like WhatsApp
    """

    CONFIG_FILE = ".whatsapp_cli_config.json"

    def __init__(
        self,
        phone_number: str | None = None,
        flow_path: str | None = None,
        model: str = "gpt-5",
        reset: bool = False,
        user_phone: str | None = None,
    ):
        """Initialize the simulator.

        Args:
            phone_number: WhatsApp business number to connect to (e.g., "+1234567890")
            flow_path: Optional path to override flow (uses channel's active flow if not provided)
            model: LLM model to use
            reset: Reset configuration (for standalone mode)
            user_phone: Optional user phone number (defaults to generated)
        """
        self.phone_number = phone_number  # Bot's WhatsApp number
        self.flow_path = Path(flow_path) if flow_path else None
        self.model = model
        self.reset = reset

        # Message queue for async behavior
        self.message_queue = Queue()
        self.processing = False
        self.shutdown_event = threading.Event()
        self._buffer_lock = threading.Lock()
        self._pending_messages: list[dict[str, Any]] = []
        self._last_message_ts: float | None = None

        # Phone numbers
        self.user_phone = user_phone or "+19995551234"  # Default user phone
        self.bot_phone = phone_number or "+0987654321"  # Will be resolved from DB if needed

        # Core components
        self.flow_processor = None
        self.app_context = None
        self.conversation_ctx = None
        self.session_manager = None
        self.redis_client = None

    def _load_or_create_config(self) -> dict[str, Any]:
        """Load existing config or create new one."""
        config_path = Path(self.CONFIG_FILE)

        if not self.reset and config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                print(f"📂 Loaded config from {self.CONFIG_FILE}")
                return config
            except Exception as e:
                print(f"⚠️  Failed to load config: {e}")

        # Create new config
        config = {
            "tenant_id": str(uuid4()),
            "channel_id": str(uuid4()),
            "flow_id": str(uuid4()),
            "user_phone": self.user_phone,
            "bot_phone": self.bot_phone,
            "created_at": datetime.now(UTC).isoformat(),
        }

        # Save config
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        print(f"💾 Created new config in {self.CONFIG_FILE}")
        return config

    async def _setup_database(
        self, config: dict[str, Any] | None = None
    ) -> ConversationContext | None:
        """Set up database - either use existing channel or create new test setup."""
        try:
            with db_session() as session:
                # Mode 1: Use existing channel by phone number
                if self.phone_number and not config:
                    return await self._setup_from_existing_channel(session)

                # Mode 2: Create/use test setup from config
                if config:
                    return await self._setup_from_config(session, config)

                # Mode 3: Create new test setup
                return await self._create_test_setup(session)

        except Exception as e:
            logger.error(f"Database setup failed: {e}", exc_info=True)
            return None

    async def _setup_from_existing_channel(self, session: Session) -> ConversationContext | None:
        """Use an existing channel from the database."""
        # Find channel by phone number - check both identifier and phone_number fields
        whatsapp_identifier = f"whatsapp:{self.phone_number}"
        channel = find_channel_instance_by_identifier(session, whatsapp_identifier)

        # If not found by identifier, try finding by phone_number field
        if not channel:
            # Try to find by phone_number field (some channels store number differently)
            # Note: phone_number is encrypted, so we need to load and compare in Python
            all_channels = (
                session.query(ChannelInstance)
                .filter(ChannelInstance.channel_type == ChannelType.whatsapp)
                .all()
            )
            for ch in all_channels:
                if ch.phone_number and ch.phone_number == self.phone_number:
                    channel = ch
                    break

        if not channel:
            print(f"❌ No channel found for number: {self.phone_number}")
            print("   Available channels:")
            # List available channels
            channels = (
                session.query(ChannelInstance)
                .filter(ChannelInstance.channel_type == ChannelType.whatsapp)
                .all()
            )
            for ch in channels:
                identifier = ch.identifier.replace("whatsapp:", "")
                phone = ch.phone_number or identifier
                tenant_info = f"{ch.tenant.owner_first_name} {ch.tenant.owner_last_name}"
                if identifier != phone:
                    print(f"     • {phone} (ID: {identifier}, Tenant: {tenant_info})")
                else:
                    print(f"     • {phone} (Tenant: {tenant_info})")
            return None

        channel_name = (
            channel.extra.get("name", channel.identifier) if channel.extra else channel.identifier
        )
        print(f"✅ Found channel: {channel_name}")
        tenant_info = f"{channel.tenant.owner_first_name} {channel.tenant.owner_last_name}"
        print(f"   Tenant: {tenant_info}")

        # Get active flow(s) for this channel
        flow = None
        flow_definition = None

        if self.flow_path:
            # Use provided flow override
            with open(self.flow_path) as f:
                flow_definition = json.load(f)
            print(f"📊 Using override flow: {self.flow_path.name}")
        else:
            # Find active flow for this tenant/channel
            flows = session.query(Flow).filter_by(tenant_id=channel.tenant_id, is_active=True).all()

            if not flows:
                print("❌ No active flows found for tenant")
                return None

            # Use first active flow (or could prompt user to choose)
            flow = flows[0]
            flow_definition = flow.definition
            print(f"📊 Using flow: {flow.name}")

            if len(flows) > 1:
                print(f"   Note: {len(flows)} flows available, using first one")

        # Setup conversation
        contact = get_or_create_contact(
            session,
            channel.tenant_id,
            external_id=f"whatsapp:{self.user_phone}",
            phone_number=self.user_phone,
            display_name="CLI User",
        )

        thread = get_or_create_thread(
            session,
            tenant_id=channel.tenant_id,
            channel_instance_id=channel.id,
            contact_id=contact.id,
            flow_id=flow.id if flow else None,
        )

        # Get project context
        config_service = TenantConfigService(session)
        project_context = config_service.get_project_context_by_tenant_id(channel.tenant_id)

        session.commit()

        return ConversationContext(
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            flow_id=flow.id if flow else uuid4(),
            thread_id=thread.id,
            contact_id=contact.id,
            flow_definition=flow_definition,
            flow_metadata={
                "flow_name": flow.name if flow else "Override Flow",
                "flow_id": str(flow.id) if flow else str(uuid4()),
                "selected_flow_id": str(flow.id)
                if flow
                else str(uuid4()),  # Add selected_flow_id for FlowProcessor
                "thread_id": str(thread.id),
            },
            project_context=project_context,
            user_phone=self.user_phone,
            bot_phone=self.phone_number,
        )

    async def _setup_from_config(
        self, session: Session, config: dict[str, Any]
    ) -> ConversationContext | None:
        """Set up from saved config file (test mode)."""
        tenant_id = UUID(config["tenant_id"])
        channel_id = UUID(config["channel_id"])
        flow_id = UUID(config["flow_id"])

        # Ensure tenant exists
        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            tenant = Tenant(
                id=tenant_id,
                owner_first_name="CLI",
                owner_last_name="Test",
                owner_email="cli@test.local",
            )
            session.add(tenant)
            session.flush()
            print(f"✅ Created tenant: {tenant_id}")
        else:
            print(f"📌 Using existing tenant: {tenant_id}")

        # Ensure channel exists
        whatsapp_identifier = f"whatsapp:{self.bot_phone}"
        channel = find_channel_instance_by_identifier(session, whatsapp_identifier)

        if not channel:
            channel = ChannelInstance(
                id=channel_id,
                tenant_id=tenant_id,
                channel_type=ChannelType.whatsapp,
                identifier=whatsapp_identifier,
                phone_number=self.bot_phone,
                extra={"cli_mode": True, "name": "WhatsApp CLI Channel"},
            )
            session.add(channel)
            session.flush()
            print(f"✅ Created channel: {channel_id}")
        else:
            channel_id = channel.id
            print(f"📌 Using existing channel: {channel_id}")

        # Load flow
        if not self.flow_path:
            print("❌ Flow path required for test mode")
            return None

        with open(self.flow_path) as f:
            flow_definition = json.load(f)

        flow = session.get(Flow, flow_id)
        if flow:
            flow.definition = flow_definition
            flow.updated_at = datetime.now(UTC)
            print(f"🔄 Updated flow: {flow_id}")
        else:
            flow = Flow(
                id=flow_id,
                tenant_id=tenant_id,
                channel_instance_id=channel_id,
                name=flow_definition.get("metadata", {}).get("name", self.flow_path.stem),
                definition=flow_definition,
                is_active=True,
                flow_id=flow_definition.get("id", str(flow_id)),
            )
            session.add(flow)
            print(f"✅ Created flow: {flow_id}")

        # Setup conversation
        contact = get_or_create_contact(
            session,
            tenant_id,
            external_id=f"whatsapp:{self.user_phone}",
            phone_number=self.user_phone,
            display_name="CLI User",
        )

        thread = get_or_create_thread(
            session,
            tenant_id=tenant_id,
            channel_instance_id=channel_id,
            contact_id=contact.id,
            flow_id=flow_id,
        )

        # Get project context
        config_service = TenantConfigService(session)
        project_context = config_service.get_project_context_by_tenant_id(tenant_id)

        # Commit all changes
        session.commit()

        # Create conversation context
        return ConversationContext(
            tenant_id=tenant_id,
            channel_id=channel_id,
            flow_id=flow_id,
            thread_id=thread.id,
            contact_id=contact.id,
            flow_definition=flow_definition,
            flow_metadata={
                "flow_name": flow.name,
                "flow_id": str(flow_id),
                "selected_flow_id": str(flow_id),  # Add selected_flow_id for FlowProcessor
                "thread_id": str(thread.id),
            },
            project_context=project_context,
            user_phone=self.user_phone,
            bot_phone=self.bot_phone,
        )

    async def _create_test_setup(self, session: Session) -> ConversationContext | None:
        """Create a new test setup when no existing channel is specified."""
        if not self.flow_path:
            print("❌ Flow path required when not using existing channel")
            return None

        # Generate new IDs
        tenant_id = uuid4()
        channel_id = uuid4()
        flow_id = uuid4()

        # Save config for reuse
        config = {
            "tenant_id": str(tenant_id),
            "channel_id": str(channel_id),
            "flow_id": str(flow_id),
            "user_phone": self.user_phone,
            "bot_phone": self.bot_phone,
            "created_at": datetime.now(UTC).isoformat(),
        }

        with open(self.CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

        print(f"💾 Created new test config in {self.CONFIG_FILE}")

        # Use the config setup method
        return await self._setup_from_config(session, config)

    async def _initialize_services(self) -> bool:
        """Initialize all required services."""
        try:
            # Load environment
            load_dotenv()
            settings = get_settings()

            # Initialize LLM
            if self.model.startswith("gpt"):
                if not os.getenv("OPENAI_API_KEY"):
                    print("❌ OPENAI_API_KEY required for GPT models")
                    return False
                chat_model = init_chat_model(self.model, model_provider="openai")
            else:
                # Try Claude/Anthropic
                if not os.getenv("ANTHROPIC_API_KEY"):
                    print("❌ ANTHROPIC_API_KEY required for Claude models")
                    return False
                chat_model = init_chat_model(self.model, model_provider="anthropic")

            llm_client = LangChainToolsLLM(chat_model)
            print(f"🤖 LLM initialized: {self.model}")

            # Initialize Redis
            redis_url = settings.redis_conn_url
            if not redis_url:
                print("❌ Redis URL not configured")
                return False

            # Test Redis connectivity first
            test_redis = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            test_redis.ping()
            print("📦 Redis connected")

            # Create RedisStore (implements ConversationStore interface)
            from app.core.state import RedisStore

            redis_store = RedisStore(redis_url)

            # Create session manager with proper ConversationStore
            self.session_manager = RedisSessionManager(redis_store)

            # Create app context
            self.app_context = AppContext(
                config_provider=None,  # Not needed for CLI
                store=redis_store,  # Use the RedisStore, not raw Redis client
                llm=llm_client,
                llm_model=self.model,
                session_policy=None,
                rate_limiter=None,
                cancellation_manager=ProcessingCancellationManager(store=redis_store),
            )

            # Initialize FlowProcessor
            self.flow_processor = FlowProcessor(
                llm_client=llm_client,
                session_manager=self.session_manager,
                cancellation_manager=self.app_context.cancellation_manager,
            )

            print("✅ All services initialized")
            return True

        except Exception as e:
            logger.error(f"Service initialization failed: {e}", exc_info=True)
            return False

    def _start_input_thread(self):
        """Start thread for non-blocking input."""
        thread = threading.Thread(target=self._input_worker, daemon=True)
        thread.start()

    async def _apply_typing_delay(self):
        """Apply tenant-configured delay before processing (simulates typing)."""
        if not self.conversation_ctx or not self.conversation_ctx.project_context:
            # Default delay if no config available
            await asyncio.sleep(60.0)
            return
        
        # Get timing configuration from project context
        project_context = self.conversation_ctx.project_context
        wait_ms = getattr(project_context, "wait_time_before_replying_ms", 60000)
        natural_delays = getattr(project_context, "natural_delays_enabled", True)
        variance_percent = getattr(project_context, "delay_variance_percent", 20)
        
        # Add natural variance if enabled
        if natural_delays and variance_percent > 0:
            import secrets
            # Use cryptographically secure random for timing variance
            variance = (secrets.randbelow(2 * variance_percent + 1) - variance_percent) / 100
            wait_ms = int(wait_ms * (1 + variance))
        
        # Ensure within reasonable bounds (100ms to 2 minutes)
        wait_ms = max(100, min(wait_ms, 120000))
        
        # Apply the delay
        await asyncio.sleep(wait_ms / 1000.0)

    def _input_worker(self):
        """Handle user input in separate thread."""
        while not self.shutdown_event.is_set():
            try:
                # Show different prompt based on processing state
                prompt = "You (typing...): " if self.processing else "You: "

                message = input(prompt).strip()

                if message:
                    if message.lower() in ["quit", "exit", "/quit", "/exit"]:
                        self.shutdown_event.set()
                        break

                    # Add to queue
                    self.message_queue.put(
                        {
                            "text": message,
                            "timestamp": time.time(),
                        }
                    )

            except (EOFError, KeyboardInterrupt):
                self.shutdown_event.set()
                break

    async def _process_messages(self):
        """Process messages from the queue."""
        while not self.shutdown_event.is_set():
            try:
                # Drain queue into buffer immediately
                while not self.message_queue.empty():
                    item = self.message_queue.get_nowait()
                    with self._buffer_lock:
                        self._pending_messages.append(item)
                        self._last_message_ts = item.get("timestamp")

                # If not currently processing and we have buffered messages, check debounce window
                if not self.processing and self._pending_messages:
                    # Wait until 60s of inactivity (configurable via project context)
                    await self._wait_for_inactivity()
                    # Aggregate buffered messages and process once
                    batch = self._flush_buffer()
                    if batch:
                        combined_text = self._aggregate_messages(batch)
                        await self._process_single_message({
                            "text": combined_text,
                            "timestamp": time.time(),
                            "skip_typing_delay": True,
                        })

                # Small delay
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Message processing error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _process_single_message(
        self,
        message_data: dict,
        *,
        capture: bool = False,
        suppress_output: bool = False,
    ) -> dict[str, Any] | None:
        """Process a single message using FlowProcessor.

        Args:
            message_data: Raw message payload from queue or caller.
            capture: When True, return structured response data for programmatic usage.
            suppress_output: When True, skip console printing (used by automated testers).

        Returns:
            Optional dictionary with response details when `capture` is True.
        """
        self.processing = True
        message_text = message_data["text"]

        # Show typing indicator unless silenced
        if not suppress_output:
            print("💭 Bot is typing...")

        response: FlowResponse | None = None
        display_payload: dict[str, Any] | None = None
        processing_time = 0.0

        try:
            # Log incoming message to database
            with db_session() as session:
                create_message(
                    session,
                    tenant_id=self.conversation_ctx.tenant_id,
                    channel_instance_id=self.conversation_ctx.channel_id,
                    thread_id=self.conversation_ctx.thread_id,
                    contact_id=self.conversation_ctx.contact_id,
                    text=message_text,
                    direction=MessageDirection.inbound,
                    status=MessageStatus.delivered,
                    provider_message_id=f"cli_in_{uuid4().hex[:8]}",
                )
                session.commit()

            # Apply tenant-configured delay before processing (like WhatsApp webhook does)
            if not message_data.get("skip_typing_delay"):
                await self._apply_typing_delay()

            # Create flow request (like webhook does)
            flow_request = FlowRequest(
                user_id=f"whatsapp:{self.user_phone}",
                user_message=message_text,
                flow_definition=self.conversation_ctx.flow_definition,
                flow_metadata=self.conversation_ctx.flow_metadata,
                tenant_id=str(self.conversation_ctx.tenant_id),
                project_context=self.conversation_ctx.project_context,
                channel_id=f"whatsapp:{self.bot_phone}",
            )

            # Process through FlowProcessor (same as webhook)
            start_time = time.time()
            response = await self.flow_processor.process_flow(flow_request, self.app_context)
            processing_time = (time.time() - start_time) * 1000
            # Display response (or capture data)
            display_payload = await self._display_response(
                response,
                processing_time,
                suppress_output=suppress_output,
            )

            # Log outbound message to database
            # Convert single message to list format for processing
            messages = []
            if response.message:
                messages.append({"text": response.message, "delay_ms": 0})
            # Also check metadata for additional messages (from LLM tool calls)
            if response.metadata and "messages" in response.metadata:
                messages = response.metadata["messages"]

            if messages:
                with db_session() as session:
                    for msg in messages:
                        create_message(
                            session,
                            tenant_id=self.conversation_ctx.tenant_id,
                            channel_instance_id=self.conversation_ctx.channel_id,
                            thread_id=self.conversation_ctx.thread_id,
                            contact_id=self.conversation_ctx.contact_id,
                            text=msg.get("text", ""),
                            direction=MessageDirection.outbound,
                            status=MessageStatus.sent,
                            provider_message_id=f"cli_out_{uuid4().hex[:8]}",
                        )
                    session.commit()

            # Check for terminal states
            if response.result == FlowProcessingResult.TERMINAL:
                if not suppress_output:
                    print("\n🎉 Flow completed successfully!")
                self.shutdown_event.set()
            elif response.result == FlowProcessingResult.ESCALATE:
                if not suppress_output:
                    print("\n🚨 Escalated to human agent")
                self.shutdown_event.set()

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            if not suppress_output:
                print(f"❌ Error: {e!s}")
            if capture:
                return {
                    "user_message": message_text,
                    "error": str(e),
                    "metadata": {},
                    "messages": [],
                    "processing_time_ms": processing_time,
                }
        finally:
            self.processing = False
            # If more messages arrived during processing, loop will pick them up on next iteration

        if capture and response is not None:
            return {
                "user_message": message_text,
                "response": response,
                "messages": (display_payload or {}).get("messages", []),
                "metadata": response.metadata or {},
                "processing_time_ms": (display_payload or {}).get(
                    "processing_time_ms", processing_time
                ),
                "result": response.result,
            }

        return None

    async def _display_response(
        self,
        response: FlowResponse,
        processing_time: float,
        *,
        suppress_output: bool = False,
    ) -> dict[str, Any]:
        """Display response like WhatsApp would and return structured info."""
        # Check metadata for messages first (from LLM tool calls)
        messages = []
        if response.metadata and "messages" in response.metadata:
            messages = response.metadata["messages"]
        # Fall back to single message if no messages in metadata
        elif response.message:
            messages.append({"text": response.message, "delay_ms": 0})

        normalized_messages: list[dict[str, Any]] = []

        # Display messages
        if messages:
            for msg in messages:
                # Simulate delay if specified
                delay_ms = msg.get("delay_ms", 0)
                if delay_ms > 0 and not suppress_output:
                    print(f"   ⏱️  [delay: {delay_ms}ms]")
                    await asyncio.sleep(delay_ms / 1000.0)

                # Display message
                text = msg.get("text", "")
                if not suppress_output:
                    print(f"📱 {text}")

                normalized_messages.append(
                    {
                        "text": text,
                        "delay_ms": delay_ms,
                    }
                )
        else:
            normalized_messages = []

        # Show processing time
        if not suppress_output:
            print(f"   ⚡ Processed in {processing_time:.0f}ms")

        # Debug info (optional)
        if hasattr(response, "metadata") and response.metadata and not suppress_output:
            if "tool_name" in response.metadata:
                print(f"   🔧 Tool: {response.metadata['tool_name']}")
            if "confidence" in response.metadata:
                conf = response.metadata["confidence"]
                if conf < 1.0:
                    print(f"   📊 Confidence: {conf:.2f}")

        return {
            "messages": normalized_messages,
            "processing_time_ms": processing_time,
            "metadata": response.metadata or {},
        }

    def _flush_buffer(self) -> list[dict[str, Any]]:
        """Atomically flush the pending message buffer."""
        with self._buffer_lock:
            batch = list(self._pending_messages)
            self._pending_messages.clear()
            self._last_message_ts = None
            return batch

    async def _wait_for_inactivity(self) -> None:
        """Wait until one minute of inactivity since the last message, resetting on new input."""
        # Resolve desired inactivity window from project context
        inactivity_ms = 60000
        if self.conversation_ctx and self.conversation_ctx.project_context:
            inactivity_ms = getattr(
                self.conversation_ctx.project_context,
                "wait_time_before_replying_ms",
                60000,
            )

        # Bound between 100ms and 120s like webhook behavior
        inactivity_ms = max(100, min(inactivity_ms, 120000))

        # Poll every 250ms for new messages, reset timer when new messages arrive
        waited = 0
        last_seen_ts = self._last_message_ts
        while True:
            await asyncio.sleep(0.25)
            waited += 250

            # If a new message has arrived, reset the wait
            if self._last_message_ts and self._last_message_ts != last_seen_ts:
                last_seen_ts = self._last_message_ts
                waited = 0
                continue

            if waited >= inactivity_ms:
                return

    def _aggregate_messages(self, messages: list[dict[str, Any]]) -> str:
        """Aggregate buffered CLI messages using same policy as webhook manager."""
        if not messages:
            return ""

        # Sort by timestamp to ensure order
        ordered = sorted(messages, key=lambda m: m.get("timestamp", 0))

        # Join with newlines to keep separate thoughts clear (matches webhook behavior)
        parts: list[str] = []
        for msg in ordered:
            text = str(msg.get("text", "")).strip()
            if text:
                parts.append(text)
        return "\n".join(parts)

    async def process_message(
        self,
        message_text: str,
        *,
        capture: bool = False,
        suppress_output: bool = False,
    ) -> dict[str, Any] | None:
        """Public helper to process a single message programmatically."""
        message_data = {
            "text": message_text,
            "timestamp": time.time(),
        }
        return await self._process_single_message(
            message_data,
            capture=capture,
            suppress_output=suppress_output,
        )

    async def run(self):
        """Run the WhatsApp simulator."""
        print("\n" + "=" * 60)
        print("📱 WhatsApp Business Simulator CLI")
        print("=" * 60)
        print("Simulating WhatsApp with production infrastructure:")
        print("  ✓ Database persistence")
        print("  ✓ Redis session management")
        print("  ✓ FlowProcessor service")
        print("  ✓ Message logging")
        print("  ✓ Async messaging")
        print("=" * 60)

        # Determine mode and setup
        config = None
        if self.phone_number:
            # Mode 1: Use existing channel
            print(f"\n📱 Connecting to WhatsApp Business: {self.phone_number}")
        elif not self.reset and Path(self.CONFIG_FILE).exists() and not self.phone_number:
            # Mode 2: Use existing config
            config = self._load_or_create_config()
            print("\n📂 Using saved configuration")
        else:
            # Mode 3: Create new test setup
            print("\n🆕 Creating new test environment")

        print("\n🔧 Setting up database...")
        self.conversation_ctx = await self._setup_database(config)
        if not self.conversation_ctx:
            print("❌ Database setup failed")
            return

        print("\n🔧 Initializing services...")
        if not await self._initialize_services():
            print("❌ Service initialization failed")
            return

        # Display ready message
        print("\n" + "=" * 60)
        print("✅ WhatsApp Simulator Ready!")
        print("=" * 60)
        print(f"📱 Your number: {self.user_phone}")
        print(f"🤖 Bot number: {self.bot_phone}")
        print(f"🏢 Tenant: {self.conversation_ctx.tenant_id}")
        if self.flow_path:
            print(f"📊 Flow: {self.flow_path.name}")
        else:
            print(f"📊 Flow: {self.conversation_ctx.flow_metadata.get('flow_name', 'Active Flow')}")
        print("=" * 60)
        print("\n💬 Start chatting! (type 'quit' to exit)")
        print("   You can type while bot is processing (like real WhatsApp)")
        print()

        # Start processing
        self._start_input_thread()

        try:
            await self._process_messages()
        except KeyboardInterrupt:
            print("\n👋 Interrupted")
        finally:
            self.shutdown_event.set()

        print("\n👋 Session ended")
        print(f"💾 All data saved to database (Tenant: {self.conversation_ctx.tenant_id})")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="WhatsApp Simulator - Connect to existing channels or create test environments",
        epilog="""
Examples:
  # Connect to existing WhatsApp channel:
  %(prog)s --phone +1234567890
  
  # Connect to existing channel with custom flow:
  %(prog)s --phone +1234567890 --flow playground/flow.json
  
  # Create test environment with flow:
  %(prog)s playground/flow.json
  
  # Use saved test configuration:
  %(prog)s playground/flow.json  # (reuses .whatsapp_cli_config.json)
  
  # Reset and create new test environment:
  %(prog)s playground/flow.json --reset
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Phone number for existing channel
    parser.add_argument(
        "--phone", "-p", type=str, help="WhatsApp Business number to connect to (e.g., +1234567890)"
    )

    # Optional flow override
    parser.add_argument(
        "--flow", "-f", type=str, help="Flow JSON file (optional with --phone, required otherwise)"
    )

    # Legacy positional argument for backward compatibility
    parser.add_argument(
        "flow_path", type=str, nargs="?", help="Flow JSON file (alternative to --flow)"
    )

    # Other options
    parser.add_argument("--model", type=str, default="gpt-5", help="LLM model (default: gpt-5)")
    parser.add_argument(
        "--reset", action="store_true", help="Reset config and create new test environment"
    )
    parser.add_argument("--user-phone", type=str, help="Your phone number (default: +19995551234)")
    parser.add_argument(
        "--list-channels", action="store_true", help="List available WhatsApp channels and exit"
    )

    args = parser.parse_args()

    # List channels mode
    if args.list_channels:
        print("\n📱 Available WhatsApp Channels:")
        print("=" * 50)
        try:
            with db_session() as session:
                channels = session.query(ChannelInstance).filter_by(channel_type="whatsapp").all()

                if not channels:
                    print("No WhatsApp channels found")
                else:
                    for ch in channels:
                        identifier = ch.identifier.replace("whatsapp:", "")
                        phone = ch.phone_number or identifier
                        tenant_info = f"{ch.tenant.owner_first_name} {ch.tenant.owner_last_name}"

                        if identifier != phone:
                            print(f"  • Phone: {phone}")
                            print(f"    ID: {identifier}")
                        else:
                            print(f"  • {phone}")
                        print(f"    Tenant: {tenant_info}")
                        print(f"    Email: {ch.tenant.owner_email}")
                        print()
        except Exception as e:
            print(f"Error listing channels: {e}")
        return 0

    # Determine flow path
    flow_path = args.flow or args.flow_path

    # Validate inputs
    if not args.phone and not flow_path:
        print("❌ Either --phone or a flow file is required")
        parser.print_help()
        return 1

    if flow_path:
        flow_file = Path(flow_path)
        if not flow_file.exists():
            print(f"❌ Flow not found: {flow_file}")
            return 1

    # Run simulator
    simulator = WhatsAppSimulatorCLI(
        phone_number=args.phone,
        flow_path=flow_path,
        model=args.model,
        reset=args.reset,
        user_phone=args.user_phone,
    )
    await simulator.run()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
