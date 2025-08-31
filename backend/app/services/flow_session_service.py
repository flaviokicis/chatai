"""Flow session management service with distributed locking and context persistence."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from app.flow_core.state import FlowContext

if TYPE_CHECKING:
    from app.core.state import ConversationStore
    from app.db.models import Flow as FlowModel

logger = logging.getLogger(__name__)


@dataclass
class FlowSession:
    """Represents an active flow session with locking and context management."""

    session_id: str
    user_id: str
    flow_id: str
    lock_key: str
    reply_id: str
    context: FlowContext | None = None
    lock_acquired: bool = False
    lock_expiry: int = 0


class FlowSessionService:
    """
    Service for managing flow sessions with distributed locking and context persistence.
    
    Handles:
    - Distributed locking to prevent concurrent processing
    - Flow context serialization/deserialization  
    - Session lifecycle management
    - Reply ID management for interruption handling
    """

    LOCK_WAIT_SECONDS = 30
    LOCK_HOLD_SECONDS = 60

    def __init__(self, store: ConversationStore):
        self.store = store

    def create_session(
        self,
        user_id: str,
        flow_model: FlowModel,
        existing_context: FlowContext | None = None
    ) -> FlowSession:
        """
        Create a new flow session with unique reply ID and session identifiers.
        
        Args:
            user_id: User identifier (phone number)
            flow_model: Database flow model
            existing_context: Optional existing flow context to restore
            
        Returns:
            FlowSession object ready for processing
        """
        reply_id = str(uuid4())
        session_id = f"flow:{user_id}:{flow_model.flow_id}"
        lock_key = f"lock:{session_id}"

        # Update current reply ID for interruption handling
        current_reply_key = f"current_reply:{user_id}"
        self.store.save("system", current_reply_key, {
            "reply_id": reply_id,
            "timestamp": int(time.time())
        })
        logger.debug("Set current reply ID %s for user %s", reply_id, user_id)

        return FlowSession(
            session_id=session_id,
            user_id=user_id,
            flow_id=flow_model.flow_id,
            lock_key=lock_key,
            reply_id=reply_id,
            context=existing_context
        )

    def acquire_lock(self, session: FlowSession) -> bool:
        """
        Acquire distributed lock for the flow session.
        
        Args:
            session: Flow session to lock
            
        Returns:
            True if lock was acquired successfully
        """
        lock_expiry = int(time.time()) + self.LOCK_HOLD_SECONDS
        session.lock_expiry = lock_expiry

        # Try to acquire lock with timeout
        for attempt in range(self.LOCK_WAIT_SECONDS):
            if hasattr(self.store, "_r"):  # Redis store
                current_time = int(time.time())

                # Try to set lock with expiry
                lock_set = self.store._r.set(
                    session.lock_key, lock_expiry, nx=True, ex=self.LOCK_HOLD_SECONDS
                )
                if lock_set:
                    session.lock_acquired = True
                    logger.debug("Acquired lock for %s", session.session_id)
                    return True

                # Check if existing lock has expired
                existing_lock = self.store._r.get(session.lock_key)
                if existing_lock:
                    try:
                        existing_expiry = int(
                            existing_lock.decode() if isinstance(existing_lock, bytes)
                            else existing_lock
                        )
                        if current_time > existing_expiry:
                            # Lock expired, try to claim it
                            if self.store._r.getset(session.lock_key, lock_expiry):
                                session.lock_acquired = True
                                logger.debug("Claimed expired lock for %s", session.session_id)
                                return True
                    except (ValueError, TypeError):
                        pass
            else:
                # Fallback for non-Redis stores - just proceed
                session.lock_acquired = True
                return True

            if attempt < self.LOCK_WAIT_SECONDS - 1:  # Don't sleep on last attempt
                time.sleep(1)

        logger.warning("Failed to acquire lock for %s, proceeding anyway", session.session_id)
        return False

    def release_lock(self, session: FlowSession) -> None:
        """
        Release the distributed lock for the flow session.
        
        Args:
            session: Flow session to unlock
        """
        if not session.lock_acquired or not hasattr(self.store, "_r"):
            return

        try:
            # Only delete if we still own the lock (check expiry)
            current_lock = self.store._r.get(session.lock_key)
            if current_lock:
                try:
                    current_expiry = int(
                        current_lock.decode() if isinstance(current_lock, bytes)
                        else current_lock
                    )
                    if current_expiry == session.lock_expiry:  # We still own this lock
                        self.store._r.delete(session.lock_key)
                        logger.debug("Released lock for %s", session.session_id)
                except (ValueError, TypeError):
                    # If we can't parse, just delete anyway
                    self.store._r.delete(session.lock_key)
        except Exception as e:
            logger.warning("Failed to release lock for %s: %s", session.session_id, e)

    def load_context(self, session: FlowSession) -> FlowContext | None:
        """
        Load existing flow context from storage.
        
        Args:
            session: Flow session to load context for
            
        Returns:
            Deserialized FlowContext or None if not found/invalid
        """
        existing_context_data = self.store.load(session.user_id, session.session_id)

        if existing_context_data and isinstance(existing_context_data, dict):
            try:
                context = FlowContext.from_dict(existing_context_data)
                logger.debug("Loaded existing flow context for session %s", session.session_id)
                session.context = context
                return context
            except Exception as e:
                logger.warning("Failed to deserialize flow context, creating new: %s", e)

        return None

    def save_context(self, session: FlowSession, context: FlowContext) -> None:
        """
        Save flow context to persistent storage.
        
        Args:
            session: Flow session
            context: Flow context to save
        """
        try:
            self.store.save(session.user_id, session.session_id, context.to_dict())
            logger.debug("Saved updated flow context for session %s", session.session_id)
        except Exception as e:
            logger.error("Failed to save flow context: %s", e)

    def clear_context(self, session: FlowSession) -> None:
        """
        Clear flow context from storage (typically on flow completion).
        
        Args:
            session: Flow session to clear
        """
        try:
            self.store.save(session.user_id, session.session_id, {})
            logger.debug("Cleared flow context on completion")
        except Exception as e:
            logger.warning("Failed to clear completed flow context: %s", e)
