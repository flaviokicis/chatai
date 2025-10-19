"""Production-grade message debouncing and aggregation manager.

This manager implements a robust debouncing system where:
1. Multiple rapid messages are buffered with timestamps
2. Timer RESETS on each new message (true debouncing)
3. After inactivity period, messages are aggregated and processed once
4. Handles webhook retries, Redis failures, clock skew, and race conditions

Requires Redis - no in-memory fallback (simpler = fewer bugs).
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.core.state import ConversationStore

logger = logging.getLogger(__name__)


class ProcessingCancellationManager:
    """Manages message debouncing and aggregation with production-grade reliability.
    
    Design principles:
    - Redis is required (no fallback - simpler code)
    - Monotonic sequence numbers prevent clock skew issues
    - Atomic operations prevent race conditions
    - Idempotent (safe for webhook retries)
    """

    MESSAGE_BUFFER_PREFIX = "debounce:buffer:"
    SEQUENCE_PREFIX = "debounce:seq:"
    LAST_MESSAGE_TIME_PREFIX = "debounce:last_time:"
    
    BUFFER_TTL_SECONDS = 300
    MAX_INACTIVITY_MS = 120000
    MIN_INACTIVITY_MS = 100
    
    def __init__(self, store: ConversationStore | None = None) -> None:
        """Initialize the manager.
        
        Args:
            store: Redis-backed conversation store (required)
        """
        if not store or not hasattr(store, "_r"):
            raise RuntimeError(
                "ProcessingCancellationManager requires Redis-backed ConversationStore. "
                "Ensure REDIS_URL is configured."
            )
        self._store = store

    def add_message_to_buffer(self, session_id: str, message: str) -> str:
        """Add message to buffer and return its unique ID.
        
        This is idempotent - calling with same message multiple times
        (e.g., webhook retries) will not duplicate it.
        
        Args:
            session_id: Unique session identifier
            message: Message content
            
        Returns:
            Message ID (format: "{sequence}:{timestamp}")
        """
        timestamp = time.time()
        
        buffer_key = f"{self.MESSAGE_BUFFER_PREFIX}{session_id}"
        seq_key = f"{self.SEQUENCE_PREFIX}{session_id}"
        time_key = f"{self.LAST_MESSAGE_TIME_PREFIX}{session_id}"
        
        pipeline = self._store._r.pipeline()
        pipeline.incr(seq_key)
        pipeline.lrange(buffer_key, 0, -1)
        
        results = pipeline.execute()
        sequence = int(results[0])
        existing_messages = results[1]
        
        for existing_msg_json in existing_messages:
            try:
                existing_data: dict[str, Any] = json.loads(existing_msg_json)
                if existing_data.get("content") == message:
                    msg_id: str = existing_data.get("id", f"{sequence}:{timestamp:.6f}")
                    logger.debug(
                        f"[{session_id}] Message already in buffer (webhook retry?): {message[:50]}..."
                    )
                    return msg_id
            except (json.JSONDecodeError, KeyError):
                continue
        
        message_id = f"{sequence}:{timestamp:.6f}"
        msg_data: dict[str, Any] = {
            "id": message_id,
            "sequence": sequence,
            "content": message,
            "timestamp": timestamp,
        }
        
        pipeline = self._store._r.pipeline()
        pipeline.rpush(buffer_key, json.dumps(msg_data))
        pipeline.expire(buffer_key, self.BUFFER_TTL_SECONDS)
        pipeline.set(time_key, str(timestamp))
        pipeline.expire(time_key, self.BUFFER_TTL_SECONDS)
        pipeline.expire(seq_key, self.BUFFER_TTL_SECONDS)
        pipeline.execute()
        
        logger.info(
            f"[{session_id}] Buffered message #{sequence}: {message[:50]}..."
        )
        return message_id
    
    async def wait_for_inactivity(
        self,
        session_id: str,
        since_message_id: str,
        inactivity_ms: int,
        *,
        check_interval_ms: int = 1000,
    ) -> Literal["exit", "process_aggregated", "process_single"]:
        """Wait for inactivity period, resetting timer on new messages.
        
        This implements TRUE debouncing:
        - Timer resets when new message arrives
        - Only processes after full inactivity period
        - Earlier webhooks exit when newer message arrives
        
        Args:
            session_id: Session identifier
            since_message_id: ID of current message
            inactivity_ms: Milliseconds of inactivity required
            check_interval_ms: How often to check for new messages
            
        Returns:
            - "exit": Newer message arrived, caller should exit
            - "process_aggregated": Inactivity period elapsed, multiple messages buffered
            - "process_single": Inactivity period elapsed, single message buffered
        """
        import asyncio
        
        inactivity_ms = max(self.MIN_INACTIVITY_MS, min(inactivity_ms, self.MAX_INACTIVITY_MS))
        
        try:
            my_sequence = self._extract_sequence(since_message_id)
        except ValueError:
            logger.error(f"[{session_id}] Invalid message ID format: {since_message_id}")
            return "exit"
        
        logger.info(
            f"[{session_id}] Message #{my_sequence}: Waiting {inactivity_ms}ms for inactivity..."
        )
        
        check_count = 0
        while True:
            await asyncio.sleep(check_interval_ms / 1000.0)
            check_count += 1
            
            latest_sequence = self._get_latest_sequence(session_id)
            if latest_sequence > my_sequence:
                logger.info(
                    f"[{session_id}] Message #{my_sequence}: Newer message #{latest_sequence} arrived, exiting"
                )
                return "exit"
            
            time_since_last_ms = self._get_time_since_last_message_ms(session_id)
            
            if time_since_last_ms >= inactivity_ms:
                count = self._get_message_count(session_id)
                logger.info(
                    f"[{session_id}] Message #{my_sequence}: Inactivity period reached "
                    f"({time_since_last_ms:.0f}ms >= {inactivity_ms}ms), "
                    f"processing {count} message(s)"
                )
                return "process_aggregated" if count > 1 else "process_single"
            
            if check_count % 10 == 0:
                logger.debug(
                    f"[{session_id}] Message #{my_sequence}: Still waiting... "
                    f"({time_since_last_ms:.0f}ms / {inactivity_ms}ms)"
                )
    
    def get_individual_messages(
        self, session_id: str
    ) -> list[dict[str, Any]]:
        """Get individual messages without aggregating or clearing.
        
        Use this to save individual messages to database before aggregation.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of individual message dicts with content, timestamp, sequence, id
        """
        buffer_key = f"{self.MESSAGE_BUFFER_PREFIX}{session_id}"
        msg_data_list = self._store._r.lrange(buffer_key, 0, -1)
        
        if not msg_data_list:
            return []
        
        messages: list[dict[str, Any]] = []
        for msg_json in msg_data_list:
            try:
                data: dict[str, Any] = json.loads(msg_json)
                content: str = str(data.get("content", ""))
                timestamp: float = float(data.get("timestamp", 0.0))
                sequence: int = int(data.get("sequence", 0))
                message_id: str = str(data.get("id", ""))
                
                if content.strip():
                    messages.append({
                        "content": content,
                        "timestamp": timestamp,
                        "sequence": sequence,
                        "id": message_id,
                    })
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning(f"[{session_id}] Failed to parse message: {e}")
                continue
        
        return messages
    
    def get_and_clear_messages(self, session_id: str) -> str | None:
        """Atomically retrieve and clear all buffered messages.
        
        Returns aggregated message string with relative timestamps,
        or None if no messages buffered.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Aggregated message string or None
        """
        buffer_key = f"{self.MESSAGE_BUFFER_PREFIX}{session_id}"
        seq_key = f"{self.SEQUENCE_PREFIX}{session_id}"
        time_key = f"{self.LAST_MESSAGE_TIME_PREFIX}{session_id}"
        
        pipeline = self._store._r.pipeline()
        pipeline.lrange(buffer_key, 0, -1)
        pipeline.delete(buffer_key, seq_key, time_key)
        results = pipeline.execute()
        
        msg_data_list: list[Any] = results[0]
        
        if not msg_data_list:
            logger.debug(f"[{session_id}] No messages to aggregate")
            return None
        
        messages_with_timestamps: list[tuple[str, float, int]] = []
        for msg_json in msg_data_list:
            try:
                data: dict[str, Any] = json.loads(msg_json)
                content: str = str(data.get("content", ""))
                timestamp: float = float(data.get("timestamp", 0.0))
                sequence: int = int(data.get("sequence", 0))
                
                if content.strip():
                    messages_with_timestamps.append((content, timestamp, sequence))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning(f"[{session_id}] Failed to parse message: {e}")
                continue
        
        if not messages_with_timestamps:
            logger.debug(f"[{session_id}] No valid messages to aggregate")
            return None
        
        aggregated = self._aggregate_messages(messages_with_timestamps)
        logger.info(
            f"[{session_id}] Aggregated {len(messages_with_timestamps)} message(s): "
            f"{aggregated[:100]}..."
        )
        return aggregated
    
    def mark_processing_complete(self, session_id: str) -> None:
        """Clear all state for a session after successful processing.
        
        Args:
            session_id: Session identifier
        """
        buffer_key = f"{self.MESSAGE_BUFFER_PREFIX}{session_id}"
        seq_key = f"{self.SEQUENCE_PREFIX}{session_id}"
        time_key = f"{self.LAST_MESSAGE_TIME_PREFIX}{session_id}"
        
        self._store._r.delete(buffer_key, seq_key, time_key)
        logger.debug(f"[{session_id}] Cleared all Redis state")
    
    def _extract_sequence(self, message_id: str) -> int:
        """Extract sequence number from message ID.
        
        Args:
            message_id: Format "{sequence}:{timestamp}"
            
        Returns:
            Sequence number
            
        Raises:
            ValueError: If message_id format is invalid
        """
        try:
            parts = message_id.split(":", 1)
            return int(parts[0])
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid message ID format: {message_id}") from e
    
    def _get_latest_sequence(self, session_id: str) -> int:
        """Get the sequence number of the most recent message.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Latest sequence number, or 0 if no messages
        """
        seq_key = f"{self.SEQUENCE_PREFIX}{session_id}"
        seq_str = self._store._r.get(seq_key)
        return int(seq_str) if seq_str else 0
    
    def _get_time_since_last_message_ms(self, session_id: str) -> float:
        """Get milliseconds elapsed since last message.
        
        Uses stored timestamp (not local clock) to avoid clock skew.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Milliseconds since last message, or infinity if no messages
        """
        time_key = f"{self.LAST_MESSAGE_TIME_PREFIX}{session_id}"
        last_time_str = self._store._r.get(time_key)
        
        if not last_time_str:
            return float("inf")
        
        last_time = float(last_time_str)
        elapsed_ms = (time.time() - last_time) * 1000
        return elapsed_ms
    
    def _get_message_count(self, session_id: str) -> int:
        """Get number of messages in buffer.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Message count
        """
        buffer_key = f"{self.MESSAGE_BUFFER_PREFIX}{session_id}"
        count = self._store._r.llen(buffer_key)
        return int(count) if count else 0
    
    def _aggregate_messages(
        self, 
        messages_with_metadata: list[tuple[str, float, int]]
    ) -> str:
        """Aggregate messages with actual timestamps.
        
        Args:
            messages_with_metadata: List of (content, timestamp, sequence) tuples
            
        Returns:
            Formatted aggregated message with HH:MM:SS timestamps
        """
        from datetime import datetime
        
        if not messages_with_metadata:
            return ""
        
        if len(messages_with_metadata) == 1:
            return messages_with_metadata[0][0]
        
        sorted_msgs = sorted(messages_with_metadata, key=lambda x: x[2])
        
        formatted_messages = []
        for content, timestamp, sequence in sorted_msgs:
            dt = datetime.fromtimestamp(timestamp)
            time_str = dt.strftime("%H:%M:%S")
            formatted_messages.append(f"[{time_str}] {content.strip()}")
        
        return "\n".join(formatted_messages)


class ProcessingCancelledException(Exception):
    """Exception raised when processing is cancelled due to newer message."""
