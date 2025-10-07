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
    """Manages message buffering and debounced aggregation.
    
    When multiple messages arrive in quick succession, this manager:
    1. Buffers all messages with timestamps
    2. Ensures only the latest message processes (earlier ones exit)
    3. Aggregates all buffered messages with relative timestamps
    """

    # Redis key prefixes
    MESSAGE_AGGREGATION_PREFIX = "msg_buffer:"
    PROCESSING_STATE_PREFIX = "processing_state:"
    CANCELLATION_PREFIX = "cancellation:"
    AGGREGATION_LOCK_PREFIX = "agg_lock:"  # Lock to ensure atomic aggregation

    def __init__(self, store=None):
        """Initialize the cancellation manager."""
        self._store = store
        self._processing_states: dict[str, ProcessingState] = {}
        self._local_cancellation_tokens: dict[str, asyncio.Event] = {}

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
                    "process_id": str(uuid.uuid4()),  # Track which process owns this
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
                logger.debug(
                    f"Cleared processing state and aggregation lock for session {session_id}"
                )
            except Exception as e:
                logger.warning(f"Failed to clear Redis state: {e}")

    def add_message_to_buffer(self, session_id: str, message: str) -> str:
        """Add a message to the buffer for aggregation.
        
        Returns:
            Message ID (timestamp-based) for tracking
        """
        current_time = time.time()
        message_id = f"{current_time:.6f}"  # Use timestamp as message ID

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
                            # Return the existing message ID
                            return data.get("id", message_id)
                    except (json.JSONDecodeError, KeyError):
                        continue

                # Add message to buffer if not already there
                msg_data = json.dumps({
                    "id": message_id,
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
                        "start_time": current_time,
                    }
                    self._store._r.setex(state_key, 300, json.dumps(new_state))

                logger.debug(f"Added message {message_id} to buffer for session {session_id}")
                return message_id
            except Exception as e:
                logger.warning(f"Failed to persist message to Redis: {e}")
                # Fallback to local memory if Redis fails
                if message not in state.messages:
                    state.messages.append(message)
                return message_id
        else:
            # In-memory fallback
            if message not in state.messages:
                state.messages.append(message)
            return message_id

    def has_newer_message(self, session_id: str, message_id: str) -> bool:
        """Check if there are any messages newer than the given message_id.
        
        Args:
            session_id: Session identifier
            message_id: Message ID to compare against (timestamp-based)
            
        Returns:
            True if there are newer messages, False otherwise
        """
        if not self._store or not hasattr(self._store, "_r"):
            # In-memory fallback - check local state
            if session_id in self._processing_states:
                state = self._processing_states[session_id]
                # Parse message_id as float timestamp
                try:
                    msg_timestamp = float(message_id)
                    return state.last_message_time > msg_timestamp
                except ValueError:
                    return False
            return False

        try:
            key = f"{self.MESSAGE_AGGREGATION_PREFIX}{session_id}"
            messages = self._store._r.lrange(key, 0, -1)
            
            if not messages:
                return False
            
            # Get the timestamp of the last message in the buffer
            try:
                last_msg_data = json.loads(messages[-1])
                last_msg_id = last_msg_data.get("id", "0")
                # Compare message IDs (which are timestamps)
                return float(last_msg_id) > float(message_id)
            except (json.JSONDecodeError, KeyError, ValueError):
                return False
                
        except Exception as e:
            logger.warning(f"Failed to check for newer messages: {e}")
            return False

    def get_message_count(self, session_id: str) -> int:
        """Get the number of messages in the buffer for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Number of messages in the buffer
        """
        if not self._store or not hasattr(self._store, "_r"):
            # In-memory fallback
            if session_id in self._processing_states:
                return len(self._processing_states[session_id].messages)
            return 0

        try:
            key = f"{self.MESSAGE_AGGREGATION_PREFIX}{session_id}"
            return int(self._store._r.llen(key) or 0)
        except Exception as e:
            logger.warning(f"Failed to get message count: {e}")
            return 0

    def get_and_clear_messages(self, session_id: str) -> str | None:
        """Get all buffered messages and clear them atomically.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Aggregated message string with timestamps, or None if no messages
        """
        if not self._store or not hasattr(self._store, "_r"):
            # In-memory fallback - note: in-memory mode doesn't preserve timestamps
            # so we fall back to simple aggregation
            if session_id in self._processing_states:
                state = self._processing_states[session_id]
                messages = state.messages[:]
                state.messages.clear()
                return self._aggregate_messages(messages) if messages else None
            return None

        try:
            key = f"{self.MESSAGE_AGGREGATION_PREFIX}{session_id}"
            
            # Get and delete atomically using pipeline
            pipeline = self._store._r.pipeline()
            pipeline.lrange(key, 0, -1)
            pipeline.delete(key)
            results = pipeline.execute()
            msg_data_list = results[0]
            
            if not msg_data_list:
                return None
            
            # Extract message contents with timestamps
            messages_with_timestamps: list[tuple[str, float]] = []
            for msg_data in msg_data_list:
                try:
                    data = json.loads(msg_data)
                    content = data.get("content")
                    timestamp = data.get("timestamp", 0.0)
                    if isinstance(content, str) and content.strip():
                        messages_with_timestamps.append((content, float(timestamp)))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
            
            if not messages_with_timestamps:
                return None
            
            return self._aggregate_messages_with_timestamps(messages_with_timestamps)
            
        except Exception as e:
            logger.warning(f"Failed to get and clear messages: {e}")
            return None

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

        # Join messages with line breaks to maintain clarity for LLM
        # This helps the LLM understand each message as a separate thought/correction
        return "\n".join(msg.strip() for msg in messages if msg.strip())

    def _aggregate_messages_with_timestamps(self, messages_with_timestamps: list[tuple[str, float]]) -> str:
        """Aggregate messages with timestamps for better context.
        
        Args:
            messages_with_timestamps: List of (message, timestamp) tuples
            
        Returns:
            Formatted string with messages and relative timestamps
        """
        if not messages_with_timestamps:
            return ""
        
        if len(messages_with_timestamps) == 1:
            return messages_with_timestamps[0][0]
        
        # Sort by timestamp to ensure chronological order
        sorted_messages = sorted(messages_with_timestamps, key=lambda x: x[1])
        
        # Get the first message timestamp as baseline
        first_timestamp = sorted_messages[0][1]
        
        # Format messages with relative timestamps
        formatted_messages = []
        for content, timestamp in sorted_messages:
            # Calculate seconds elapsed since first message
            elapsed = timestamp - first_timestamp
            
            if elapsed < 1.0:
                # First message or very quick (< 1 second)
                formatted_messages.append(content.strip())
            else:
                # Show relative timestamp for subsequent messages
                if elapsed < 60:
                    time_str = f"+{int(elapsed)}s"
                else:
                    minutes = int(elapsed / 60)
                    seconds = int(elapsed % 60)
                    time_str = f"+{minutes}m{seconds}s" if seconds > 0 else f"+{minutes}m"
                
                formatted_messages.append(f"[{time_str}] {content.strip()}")
        
        return "\n".join(formatted_messages)

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
                logger.info(
                    f"Processing cancelled during {stage} for session {session_id} (local token)"
                )
                raise ProcessingCancelledException(f"Processing cancelled during {stage}")

        # Check local state
        if session_id in self._processing_states:
            state = self._processing_states[session_id]
            if state.cancellation_token and state.cancellation_token.is_set():
                logger.info(
                    f"Processing cancelled during {stage} for session {session_id} (local state)"
                )
                raise ProcessingCancelledException(f"Processing cancelled during {stage}")

        # Also check Redis for cross-process cancellation
        if self._store and hasattr(self._store, "_r"):
            try:
                cancel_key = f"{self.CANCELLATION_PREFIX}{session_id}"
                if self._store._r.get(cancel_key):
                    logger.info(
                        f"Processing cancelled during {stage} for session {session_id} (Redis flag)"
                    )
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
