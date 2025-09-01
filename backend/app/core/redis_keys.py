"""
Centralized Redis key builder to ensure consistency across the application.

This module provides a single source of truth for Redis key patterns,
eliminating the inconsistencies that have been causing issues.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RedisKeyBuilder:
    """
    Centralized Redis key builder for consistent key generation.
    
    This ensures all parts of the application use the same key patterns
    for the same purposes, eliminating the chaos of inconsistent keys.
    """
    
    namespace: str = "chatai"
    
    def conversation_state_key(self, user_id: str, session_id: str) -> str:
        """
        Build conversation state key.
        
        Args:
            user_id: User identifier (e.g., "whatsapp:5522988544370")
            session_id: Session identifier (e.g., "flow:whatsapp:5522988544370:flow.atendimento_luminarias")
            
        Returns:
            Redis key for conversation state
        """
        return f"{self.namespace}:state:{user_id}:{session_id}"
    
    def conversation_meta_key(self, user_id: str, agent_type: str) -> str:
        """
        Build conversation metadata key.
        
        Args:
            user_id: User identifier
            agent_type: Agent type (e.g., "flow", "chat", etc.)
            
        Returns:
            Redis key for conversation metadata
        """
        return f"{self.namespace}:state:{user_id}:meta:{agent_type}"
    
    def conversation_history_key(self, session_id: str) -> str:
        """
        Build conversation history key for LangChain.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Redis key for conversation history
        """
        return f"{self.namespace}:history:{session_id}"
    
    def current_reply_key(self, user_id: str) -> str:
        """
        Build current reply key for interruption handling.
        
        Args:
            user_id: User identifier
            
        Returns:
            Redis key for current reply tracking
        """
        return f"{self.namespace}:state:system:current_reply:{user_id}"
    
    def get_conversation_patterns(self, user_id: str, flow_id: str | None = None) -> list[str]:
        """
        Get all Redis key patterns for a conversation to enable proper cleanup.
        
        Args:
            user_id: User identifier (e.g., "whatsapp:5522988544370")
            flow_id: Optional flow identifier (e.g., "flow.atendimento_luminarias")
            
        Returns:
            List of Redis key patterns for deletion
        """
        patterns = []
        
        # Extract phone number for broader matching
        phone_number = user_id.replace("whatsapp:", "").replace("+", "")
        
        if flow_id:
            # Flow-specific patterns
            patterns.extend([
                # Match any state key containing the phone number and flow
                f"{self.namespace}:state:*{phone_number}*{flow_id}*",
                # Match full user_id patterns
                f"{self.namespace}:state:*{user_id}*{flow_id}*",
                # Meta keys for flow
                f"{self.namespace}:state:{user_id}:meta:flow",
                f"{self.namespace}:state:{user_id}:meta:*",
                # History patterns
                f"{self.namespace}:history:*{phone_number}*{flow_id}*",
                f"{self.namespace}:history:*{user_id}*{flow_id}*",
            ])
        else:
            # All conversations for user
            patterns.extend([
                f"{self.namespace}:state:*{phone_number}*",
                f"{self.namespace}:state:*{user_id}*",
                f"{self.namespace}:history:*{phone_number}*",
                f"{self.namespace}:history:*{user_id}*",
            ])
        
        # Always include current reply key
        patterns.append(self.current_reply_key(user_id))
        
        # Events (if any)
        patterns.append(f"{self.namespace}:events:{user_id}")
        
        return patterns
    
    def parse_conversation_key(self, redis_key: str) -> dict[str, str] | None:
        """
        Parse a Redis conversation key to extract components.
        
        Args:
            redis_key: Full Redis key
            
        Returns:
            Dict with parsed components or None if not a conversation key
        """
        if not redis_key.startswith(f"{self.namespace}:state:"):
            return None
            
        # Remove namespace prefix
        remainder = redis_key[len(f"{self.namespace}:state:"):]
        
        # Skip system keys
        if remainder.startswith("system:"):
            return None
            
        # Skip meta keys
        if ":meta:" in remainder:
            return None
        
        # Look for flow pattern
        flow_match = remainder.find(":flow:")
        if flow_match != -1:
            user_id = remainder[:flow_match]
            session_id = remainder[flow_match + 1:]  # Include "flow:" prefix
            
            # Extract flow_id from session_id
            flow_parts = session_id.split(":")
            if len(flow_parts) >= 3:
                flow_id = flow_parts[-1]  # Last part is the flow name
                agent_type = "flow"  # Proper agent type
            else:
                flow_id = session_id
                agent_type = "flow"
                
            return {
                "user_id": user_id,
                "session_id": session_id,
                "agent_type": agent_type,
                "flow_id": flow_id,
                "redis_key": redis_key
            }
        
        # Legacy format
        parts = remainder.rsplit(":", 1)
        if len(parts) == 2:
            return {
                "user_id": parts[0],
                "session_id": parts[1],
                "agent_type": parts[1],
                "flow_id": None,
                "redis_key": redis_key
            }
        
        return None


# Global instance
redis_keys = RedisKeyBuilder()
