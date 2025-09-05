"""Manager for handling processing cancellation when rapid messages arrive."""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProcessingState:
    """State of a processing session."""
    is_processing: bool = False
    cancellation_token: asyncio.Event | None = None
    start_time: float = field(default_factory=time.time)
    messages: list[str] = field(default_factory=list)
    last_message_time: float = field(default_factory=time.time)


class ProcessingCancellationManager:
    """Manages cancellation of in-progress processing when new messages arrive."""

    # Time windows for message handling
    RAPID_MESSAGE_WINDOW = 120.0  # 2 minutes - messages within this window get concatenated
    MESSAGE_AGGREGATION_PREFIX = "msg_buffer:"
    PROCESSING_STATE_PREFIX = "processing_state:"
    CANCELLATION_PREFIX = "cancellation:"
    AGGREGATION_LOCK_PREFIX = "agg_lock:"  # Lock to ensure only one request processes aggregation

    def __init__(self, store=None):
        """Initialize the cancellation manager."""
        self._store = store
        self._processing_states: dict[str, ProcessingState] = {}
        self._local_cancellation_tokens: dict[str, asyncio.Event] = {}

    def should_cancel_processing(self, session_id: str) -> bool:
        """Check if we should cancel ongoing processing for this session."""
        if not self._store or not hasattr(self._store, "_r"):
            # Fallback to in-memory if Redis not available
            if session_id not in self._processing_states:
                return False
            state = self._processing_states[session_id]
            if not state.is_processing:
                return False
            time_since_last = time.time() - state.last_message_time
            return time_since_last < self.RAPID_MESSAGE_WINDOW

        try:
            # Check Redis message buffer for rapid succession
            buf_key = f"{self.MESSAGE_AGGREGATION_PREFIX}{session_id}"
            try:
                msg_count = int(self._store._r.llen(buf_key) or 0)
            except Exception:
                msg_count = 0

            last_time = None
            if msg_count > 0:
                try:
                    last_raw = self._store._r.lindex(buf_key, -1)
                    if last_raw:
                        data = json.loads(last_raw)
                        last_time = float(data.get("timestamp", 0))
                except Exception:
                    last_time = None

            # Check Redis for processing state
            state_key = f"{self.PROCESSING_STATE_PREFIX}{session_id}"
            state_data = self._store._r.get(state_key)

            if not state_data:
                # If we have at least two recent messages in buffer, cancel anyway to aggregate
                if msg_count >= 2 and last_time:
                    time_since_last = time.time() - last_time
                    return time_since_last < self.RAPID_MESSAGE_WINDOW
                return False

            state = json.loads(state_data)
            is_processing = bool(state.get("is_processing", False))
            if not is_processing:
                # If multiple messages are queued rapidly, cancel to aggregate
                if msg_count >= 2 and last_time:
                    time_since_last = time.time() - last_time
                    return time_since_last < self.RAPID_MESSAGE_WINDOW
                return False

            # Check if the last message was recent (rapid succession)
            last_message_time = last_time if last_time is not None else state.get("last_message_time", 0)
            time_since_last = time.time() - float(last_message_time or 0)
            should_cancel = time_since_last < self.RAPID_MESSAGE_WINDOW

            if should_cancel:
                logger.info(f"Should cancel processing for session {session_id}: last message {time_since_last:.1f}s ago")

            return should_cancel
        except Exception as e:
            logger.warning(f"Failed to check Redis processing state: {e}")
            return False

    def create_cancellation_token(self, session_id: str) -> asyncio.Event:
        """Create a cancellation token for a processing session."""
        # Always create a local event for this specific process
        cancellation_token = asyncio.Event()
        self._local_cancellation_tokens[session_id] = cancellation_token

        # Update local state
        if session_id not in self._processing_states:
            self._processing_states[session_id] = ProcessingState()

        state = self._processing_states[session_id]
        state.cancellation_token = cancellation_token
        state.is_processing = True
        state.start_time = time.time()

        # Also update Redis state for cross-process coordination
        if self._store and hasattr(self._store, "_r"):
            try:
                state_key = f"{self.PROCESSING_STATE_PREFIX}{session_id}"
                state_data = {
                    "is_processing": True,
                    "start_time": state.start_time,
                    "last_message_time": state.last_message_time,
                    "process_id": str(uuid.uuid4())  # Track which process owns this
                }
                self._store._r.setex(state_key, 300, json.dumps(state_data))  # 5 min expiry
                logger.info(f"Created cancellation token for session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to update Redis processing state: {e}")

        return cancellation_token

    def cancel_processing(self, session_id: str) -> bool:
        """Cancel ongoing processing for a session."""
        cancelled = False

        # Cancel local token if exists
        if session_id in self._local_cancellation_tokens:
            token = self._local_cancellation_tokens[session_id]
            if not token.is_set():
                token.set()
                cancelled = True

        # Also cancel in local state
        if session_id in self._processing_states:
            state = self._processing_states[session_id]
            if state.cancellation_token and not state.cancellation_token.is_set():
                state.cancellation_token.set()
                cancelled = True

        # Set cancellation flag in Redis for other processes to see
        if self._store and hasattr(self._store, "_r"):
            try:
                cancel_key = f"{self.CANCELLATION_PREFIX}{session_id}"
                self._store._r.setex(cancel_key, 60, "1")  # 1 minute expiry

                # Also update processing state
                state_key = f"{self.PROCESSING_STATE_PREFIX}{session_id}"
                state_data = self._store._r.get(state_key)
                if state_data:
                    state = json.loads(state_data)
                    state["is_processing"] = False
                    state["cancelled_at"] = time.time()
                    self._store._r.setex(state_key, 300, json.dumps(state))

                logger.info(f"Cancelled processing for session {session_id} (Redis notified)")
                cancelled = True
            except Exception as e:
                logger.warning(f"Failed to set Redis cancellation flag: {e}")

        if cancelled:
            logger.info(f"Successfully cancelled processing for session {session_id}")

        return cancelled

    def mark_processing_complete(self, session_id: str) -> None:
        """Mark that processing is complete for a session."""
        # Clear local state
        if session_id in self._processing_states:
            state = self._processing_states[session_id]
            state.is_processing = False
            state.cancellation_token = None
            # Clear messages after successful processing
            state.messages.clear()

        # Clear local cancellation token
        if session_id in self._local_cancellation_tokens:
            del self._local_cancellation_tokens[session_id]

        # Clear Redis state including aggregation lock
        if self._store and hasattr(self._store, "_r"):
            try:
                state_key = f"{self.PROCESSING_STATE_PREFIX}{session_id}"
                cancel_key = f"{self.CANCELLATION_PREFIX}{session_id}"
                lock_key = f"{self.AGGREGATION_LOCK_PREFIX}{session_id}"
                buffer_key = f"{self.MESSAGE_AGGREGATION_PREFIX}{session_id}"

                # Delete all related keys
                self._store._r.delete(state_key, cancel_key, lock_key, buffer_key)
                logger.debug(f"Cleared processing state and aggregation lock for session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to clear Redis state: {e}")

    def add_message_to_buffer(self, session_id: str, message: str) -> None:
        """Add a message to the buffer for aggregation."""
        current_time = time.time()

        # Update local state
        if session_id not in self._processing_states:
            self._processing_states[session_id] = ProcessingState()

        state = self._processing_states[session_id]
        state.last_message_time = current_time

        # Use Redis as the single source of truth to avoid duplicates
        if self._store and hasattr(self._store, "_r"):
            try:
                # Check if this exact message is already in the buffer (avoid duplicates)
                key = f"{self.MESSAGE_AGGREGATION_PREFIX}{session_id}"
                existing_messages = self._store._r.lrange(key, 0, -1)
                for existing in existing_messages:
                    try:
                        data = json.loads(existing)
                        if data.get("content") == message:
                            logger.debug(f"Message already in buffer, skipping: {message[:50]}...")
                            return
                    except (json.JSONDecodeError, KeyError):
                        continue

                # Add message to buffer if not already there
                msg_data = json.dumps({
                    "content": message,
                    "timestamp": current_time
                })
                self._store._r.rpush(key, msg_data)
                self._store._r.expire(key, 300)  # 5 minute expiry

                # Update processing state with last message time
                state_key = f"{self.PROCESSING_STATE_PREFIX}{session_id}"
                state_data = self._store._r.get(state_key)
                if state_data:
                    existing_state = json.loads(state_data)
                    existing_state["last_message_time"] = current_time
                    self._store._r.setex(state_key, 300, json.dumps(existing_state))
                else:
                    # Create new state if doesn't exist
                    new_state = {
                        "is_processing": False,
                        "last_message_time": current_time,
                        "start_time": current_time
                    }
                    self._store._r.setex(state_key, 300, json.dumps(new_state))

                logger.debug(f"Added message to buffer for session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to persist message to Redis: {e}")
                # Fallback to local memory if Redis fails
                if message not in state.messages:
                    state.messages.append(message)

    def is_aggregation_available(self, session_id: str) -> bool:
        """Check if aggregation can be claimed for a session."""
        if not self._store or not hasattr(self._store, "_r"):
            return True  # In-memory mode is always available

        try:
            lock_key = f"{self.AGGREGATION_LOCK_PREFIX}{session_id}"
            # Check if lock exists
            return not bool(self._store._r.exists(lock_key))
        except Exception:
            return True  # Default to available on error

    def try_claim_aggregation(self, session_id: str) -> str | None:
        """Try to atomically claim and get aggregated messages.
        
        Returns the aggregated messages if successfully claimed, None if another request already claimed them.
        """
        if not self._store or not hasattr(self._store, "_r"):
            return self._get_aggregated_from_memory(session_id)

        try:
            # Use a unique ID for this aggregation attempt
            claim_id = str(uuid.uuid4())
            lock_key = f"{self.AGGREGATION_LOCK_PREFIX}{session_id}"

            # Try to set the lock (expires in 30 seconds to prevent deadlocks)
            # Lock is properly cleared when mark_processing_complete is called
            if not self._store._r.set(lock_key, claim_id, nx=True, ex=30):
                # Another request already has the lock
                logger.debug(f"Another request is already processing aggregation for {session_id}")
                return None

            # We have the lock, get and clear the messages atomically
            key = f"{self.MESSAGE_AGGREGATION_PREFIX}{session_id}"
            pipeline = self._store._r.pipeline()
            pipeline.lrange(key, 0, -1)
            pipeline.delete(key)
            results = pipeline.execute()
            msg_data_list = results[0]

            if not msg_data_list:
                # No messages to aggregate, release lock
                self._store._r.delete(lock_key)
                return None

            messages: list[str] = []
            for msg_data in msg_data_list:
                try:
                    data = json.loads(msg_data)
                    content = data.get("content")
                    if isinstance(content, str) and content.strip():
                        messages.append(content)
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

            if not messages:
                # No valid messages, release lock
                self._store._r.delete(lock_key)
                return None

            # Successfully got messages, lock will expire naturally
            return self._aggregate_messages(messages)

        except Exception as e:
            logger.warning(f"Failed to claim aggregation: {e}")
            return None

    def get_aggregated_messages(self, session_id: str) -> str:
        """Get all buffered messages aggregated intelligently."""
        # Try to claim the aggregation
        result = self.try_claim_aggregation(session_id)
        if result is not None:
            return result

        # If we couldn't claim it, return empty (another request is handling it)
        return ""

    def _get_aggregated_from_memory(self, session_id: str) -> str:
        """Fallback to get aggregated messages from memory."""
        messages: list[str] = []

        # Get messages from local memory
        if session_id in self._processing_states and self._processing_states[session_id].messages:
            messages = self._processing_states[session_id].messages.copy()
            self._processing_states[session_id].messages.clear()

        return self._aggregate_messages(messages) if messages else ""

    def _aggregate_messages(self, messages: list[str]) -> str:
        """Aggregate multiple messages intelligently."""

        if not messages:
            return ""

        # Deduplicate consecutive identical messages while preserving order
        deduped: list[str] = []
        last: str | None = None
        for msg in messages:
            if msg != last:
                deduped.append(msg)
                last = msg

        # Intelligent aggregation
        return self._aggregate_messages_intelligently(deduped)

    def _aggregate_messages_intelligently(self, messages: list[str]) -> str:
        """Simply concatenate messages sent in rapid succession."""
        if not messages:
            return ""

        if len(messages) == 1:
            return messages[0]

        # Just join all messages with a space
        # The LLM can figure out the context from the concatenated messages
        return " ".join(msg.strip() for msg in messages if msg.strip())

    def check_cancellation_and_raise(self, session_id: str, stage: str = "processing") -> None:
        """
        Check if processing was cancelled and raise an exception if so.
        
        Args:
            session_id: Session to check
            stage: Stage name for logging (e.g., "naturalizing", "sending")
            
        Raises:
            ProcessingCancelledException: If processing was cancelled
        """
        # Check local cancellation token first
        if session_id in self._local_cancellation_tokens:
            token = self._local_cancellation_tokens[session_id]
            if token.is_set():
                logger.info(f"Processing cancelled during {stage} for session {session_id} (local token)")
                raise ProcessingCancelledException(f"Processing cancelled during {stage}")

        # Check local state
        if session_id in self._processing_states:
            state = self._processing_states[session_id]
            if state.cancellation_token and state.cancellation_token.is_set():
                logger.info(f"Processing cancelled during {stage} for session {session_id} (local state)")
                raise ProcessingCancelledException(f"Processing cancelled during {stage}")

        # Also check Redis for cross-process cancellation
        if self._store and hasattr(self._store, "_r"):
            try:
                cancel_key = f"{self.CANCELLATION_PREFIX}{session_id}"
                if self._store._r.get(cancel_key):
                    logger.info(f"Processing cancelled during {stage} for session {session_id} (Redis flag)")
                    raise ProcessingCancelledException(f"Processing cancelled during {stage}")
            except ProcessingCancelledException:
                raise  # Re-raise the cancellation
            except Exception as e:
                logger.warning(f"Failed to check Redis cancellation flag: {e}")

    def clear_cancellation_flag(self, session_id: str) -> None:
        """Clear the cancellation flag for a session to allow processing to continue."""
        # Clear Redis cancellation flag
        if self._store and hasattr(self._store, "_r"):
            try:
                cancel_key = f"{self.CANCELLATION_PREFIX}{session_id}"
                self._store._r.delete(cancel_key)
                logger.debug(f"Cleared cancellation flag for session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to clear cancellation flag: {e}")

    def clear_session(self, session_id: str) -> None:
        """Clear all data for a session."""
        if session_id in self._processing_states:
            del self._processing_states[session_id]

        # Clear Redis buffer
        if self._store and hasattr(self._store, "_r"):
            try:
                key = f"{self.MESSAGE_AGGREGATION_PREFIX}{session_id}"
                self._store._r.delete(key)
            except Exception:
                pass


class ProcessingCancelledException(Exception):
    """Exception raised when processing is cancelled."""
