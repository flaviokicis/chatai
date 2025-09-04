"""Manager for handling processing cancellation when rapid messages arrive."""

import asyncio
import time
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
import json

logger = logging.getLogger(__name__)


@dataclass
class ProcessingState:
    """State of a processing session."""
    is_processing: bool = False
    cancellation_token: Optional[asyncio.Event] = None
    start_time: float = field(default_factory=time.time)
    messages: list[str] = field(default_factory=list)
    last_message_time: float = field(default_factory=time.time)


class ProcessingCancellationManager:
    """Manages cancellation of in-progress processing when new messages arrive."""
    
    # Time windows for message handling
    RAPID_MESSAGE_WINDOW = 120.0  # 2 minutes - messages within this window get concatenated
    MESSAGE_AGGREGATION_PREFIX = "msg_buffer:"
    
    def __init__(self, store=None):
        """Initialize the cancellation manager."""
        self._store = store
        self._processing_states: Dict[str, ProcessingState] = {}
    
    def should_cancel_processing(self, session_id: str) -> bool:
        """Check if we should cancel ongoing processing for this session."""
        if session_id not in self._processing_states:
            return False
        
        state = self._processing_states[session_id]
        if not state.is_processing:
            return False
        
        # Check if the last message was recent (rapid succession)
        time_since_last = time.time() - state.last_message_time
        return time_since_last < self.RAPID_MESSAGE_WINDOW
    
    def create_cancellation_token(self, session_id: str) -> asyncio.Event:
        """Create a cancellation token for a processing session."""
        if session_id not in self._processing_states:
            self._processing_states[session_id] = ProcessingState()
        
        state = self._processing_states[session_id]
        state.cancellation_token = asyncio.Event()
        state.is_processing = True
        state.start_time = time.time()
        
        return state.cancellation_token
    
    def cancel_processing(self, session_id: str) -> bool:
        """Cancel ongoing processing for a session."""
        if session_id not in self._processing_states:
            return False
        
        state = self._processing_states[session_id]
        if state.cancellation_token and not state.cancellation_token.is_set():
            state.cancellation_token.set()
            logger.info(f"Cancelled processing for session {session_id}")
            return True
        
        return False
    
    def mark_processing_complete(self, session_id: str) -> None:
        """Mark that processing is complete for a session."""
        if session_id in self._processing_states:
            state = self._processing_states[session_id]
            state.is_processing = False
            state.cancellation_token = None
            # Clear messages after successful processing
            state.messages.clear()
    
    def add_message_to_buffer(self, session_id: str, message: str) -> None:
        """Add a message to the buffer for aggregation."""
        if session_id not in self._processing_states:
            self._processing_states[session_id] = ProcessingState()
        
        state = self._processing_states[session_id]
        state.messages.append(message)
        state.last_message_time = time.time()
        
        # Also persist to Redis if available
        if self._store and hasattr(self._store, "_r"):
            try:
                key = f"{self.MESSAGE_AGGREGATION_PREFIX}{session_id}"
                msg_data = json.dumps({
                    "content": message,
                    "timestamp": time.time()
                })
                self._store._r.rpush(key, msg_data)
                self._store._r.expire(key, 300)  # 5 minute expiry
            except Exception as e:
                logger.warning(f"Failed to persist message to Redis: {e}")
    
    def get_aggregated_messages(self, session_id: str) -> str:
        """Get all buffered messages aggregated intelligently."""
        messages = []
        
        # Get from memory first
        if session_id in self._processing_states:
            messages = self._processing_states[session_id].messages.copy()
        
        # Also check Redis for any persisted messages
        if self._store and hasattr(self._store, "_r") and not messages:
            try:
                key = f"{self.MESSAGE_AGGREGATION_PREFIX}{session_id}"
                msg_data_list = self._store._r.lrange(key, 0, -1)
                if msg_data_list:
                    for msg_data in msg_data_list:
                        try:
                            data = json.loads(msg_data)
                            messages.append(data["content"])
                        except (json.JSONDecodeError, KeyError):
                            continue
                    # Clear Redis buffer after reading
                    self._store._r.delete(key)
            except Exception as e:
                logger.warning(f"Failed to retrieve messages from Redis: {e}")
        
        if not messages:
            return ""
        
        # Intelligent aggregation
        return self._aggregate_messages_intelligently(messages)
    
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
        if session_id in self._processing_states:
            state = self._processing_states[session_id]
            if state.cancellation_token and state.cancellation_token.is_set():
                logger.info(f"Processing cancelled during {stage} for session {session_id}")
                raise ProcessingCancelledException(f"Processing cancelled during {stage}")
    
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
    pass
