"""Message deduplication service for preventing duplicate webhook processing."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.state import ConversationStore

logger = logging.getLogger(__name__)


class MessageDeduplicationService:
    """
    Service for handling message deduplication across different messaging platforms.
    
    Prevents duplicate processing of webhooks by tracking message IDs and
    fallback heuristics for platforms that don't provide reliable message IDs.
    """
    
    # TTL for message ID based deduplication (5 minutes)
    MESSAGE_ID_TTL_SECONDS = 300
    
    # TTL for fallback deduplication (30 seconds)  
    FALLBACK_TTL_SECONDS = 30
    
    def __init__(self, store: ConversationStore):
        self.store = store
    
    def is_duplicate_message(
        self, 
        message_id: str | None,
        sender_number: str,
        receiver_number: str, 
        params: dict[str, Any],
        client_ip: str = "unknown"
    ) -> bool:
        """
        Check if a message has already been processed recently.
        
        Args:
            message_id: Platform-specific message identifier
            sender_number: Sender's phone number  
            receiver_number: Receiver's phone number
            params: Full webhook parameters for fallback hashing
            client_ip: Client IP for logging
            
        Returns:
            True if message should be skipped as duplicate, False otherwise
        """
        current_time = time.time()
        
        if message_id:
            return self._check_message_id_duplicate(message_id, current_time, client_ip)
        else:
            logger.warning(
                "No message ID found for deduplication in webhook from IP=%s, params keys: %s",
                client_ip, list(params.keys())
            )
            return self._check_fallback_duplicate(
                sender_number, receiver_number, params, current_time, client_ip
            )
    
    def _check_message_id_duplicate(
        self, message_id: str, current_time: float, client_ip: str
    ) -> bool:
        """Check for duplicates using message ID."""
        logger.debug("Processing webhook with message_id=%s from IP=%s", message_id, client_ip)
        
        dedup_key = f"webhook_processed:{message_id}"
        existing = self.store.load("system", dedup_key)
        
        if existing and isinstance(existing, dict):
            processed_at = existing.get("processed_at", 0)
            if current_time - processed_at < self.MESSAGE_ID_TTL_SECONDS:
                logger.info(
                    "Skipping duplicate webhook for message_id=%s from IP=%s (processed %ds ago)",
                    message_id, client_ip, int(current_time - processed_at)
                )
                return True
        
        # Mark message as being processed
        self.store.save("system", dedup_key, {"processed_at": int(current_time)})
        logger.debug("Marked message %s as processed for deduplication", message_id)
        return False
    
    def _check_fallback_duplicate(
        self,
        sender_number: str,
        receiver_number: str,
        params: dict[str, Any],
        current_time: float,
        client_ip: str
    ) -> bool:
        """Check for duplicates using fallback heuristics when no message ID available."""
        fallback_key = f"{sender_number}:{receiver_number}:{hash(str(params))}"
        dedup_key = f"webhook_processed:{fallback_key}"
        
        existing = self.store.load("system", dedup_key)
        if existing and isinstance(existing, dict):
            processed_at = existing.get("processed_at", 0)
            if current_time - processed_at < self.FALLBACK_TTL_SECONDS:
                logger.info(
                    "Skipping likely duplicate webhook (no message_id) from IP=%s (processed %ds ago)",
                    client_ip, int(current_time - processed_at)
                )
                return True
        
        # Mark as processed with shorter TTL
        self.store.save("system", dedup_key, {"processed_at": int(current_time)})
        return False
