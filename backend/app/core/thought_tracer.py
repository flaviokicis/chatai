"""
Thought tracing system for capturing and storing agent reasoning and decision-making processes.

This module provides functionality to:
- Capture agent thoughts, tool selections, and reasoning
- Store traces in Redis with conversation context
- Retrieve traces for debugging and analysis
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.core.state import RedisStore


@dataclass
class AgentThought:
    """Represents a single agent thought/reasoning step."""
    
    id: str
    timestamp: str
    user_id: str
    session_id: str
    agent_type: str
    
    # Context
    user_message: str
    current_state: Dict[str, Any]
    available_tools: List[str]
    
    # Decision making
    reasoning: str
    selected_tool: str
    tool_args: Dict[str, Any]
    confidence: Optional[float] = None
    
    # Results
    tool_result: Optional[str] = None
    agent_response: Optional[str] = None
    errors: Optional[List[str]] = None
    
    # Metadata
    model_name: str = "unknown"
    processing_time_ms: Optional[int] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ConversationTrace:
    """Represents a complete conversation trace with all thoughts."""
    
    user_id: str
    session_id: str
    agent_type: str
    started_at: str
    last_activity: str
    thoughts: List[AgentThought]
    total_thoughts: int


class ThoughtTracer:
    """Manages thought tracing for agent interactions."""
    
    def __init__(self, redis_store: RedisStore):
        self.redis_store = redis_store
        self._redis = redis_store._r
        self._namespace = redis_store._ns
    
    def _trace_key(self, user_id: str, agent_type: str) -> str:
        """Generate Redis key for conversation trace."""
        return f"{self._namespace}:trace:{user_id}:{agent_type}"
    
    def start_thought(
        self,
        user_id: str,
        session_id: str,
        agent_type: str,
        user_message: str,
        current_state: Dict[str, Any],
        available_tools: List[str],
        model_name: str = "unknown"
    ) -> str:
        """Start a new thought process and return thought ID."""
        thought_id = str(uuid4())
        
        thought = AgentThought(
            id=thought_id,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            session_id=session_id,
            agent_type=agent_type,
            user_message=user_message,
            current_state=current_state,
            available_tools=available_tools,
            reasoning="",  # Will be filled when tool is selected
            selected_tool="",  # Will be filled when tool is selected
            tool_args={},  # Will be filled when tool is selected
            model_name=model_name
        )
        
        # Store the thought temporarily (will be completed later)
        temp_key = f"{self._namespace}:temp_thought:{thought_id}"
        self._redis.setex(
            temp_key, 
            300,  # 5 minutes TTL for temp thoughts
            json.dumps(asdict(thought), ensure_ascii=False)
        )
        
        return thought_id
    
    def complete_thought(
        self,
        thought_id: str,
        reasoning: str,
        selected_tool: str,
        tool_args: Dict[str, Any],
        tool_result: Optional[str] = None,
        agent_response: Optional[str] = None,
        errors: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        processing_time_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Complete a thought with reasoning and results."""
        temp_key = f"{self._namespace}:temp_thought:{thought_id}"
        
        try:
            # Get the temporary thought
            temp_data = self._redis.get(temp_key)
            if not temp_data:
                # Thought expired or doesn't exist, skip silently
                return
            
            thought_dict = json.loads(temp_data.decode('utf-8') if isinstance(temp_data, bytes) else temp_data)
            
            # Update with completion data
            thought_dict.update({
                "reasoning": reasoning,
                "selected_tool": selected_tool,
                "tool_args": tool_args,
                "tool_result": tool_result,
                "agent_response": agent_response,
                "errors": errors or [],
                "confidence": confidence,
                "processing_time_ms": processing_time_ms,
                "metadata": metadata or {}
            })
            
            thought = AgentThought(**thought_dict)
            
            # Store in permanent trace
            self._store_thought(thought)
            
            # Clean up temporary thought
            self._redis.delete(temp_key)
            
        except Exception as e:
            # Don't fail the main process if tracing fails
            print(f"Warning: Failed to complete thought {thought_id}: {e}")
    
    def _store_thought(self, thought: AgentThought) -> None:
        """Store a completed thought in the conversation trace."""
        trace_key = self._trace_key(thought.user_id, thought.agent_type)
        
        try:
            # Get existing trace or create new one
            existing_data = self._redis.get(trace_key)
            if existing_data:
                trace_data = json.loads(existing_data.decode('utf-8') if isinstance(existing_data, bytes) else existing_data)
                thoughts = trace_data.get("thoughts", [])
            else:
                thoughts = []
                trace_data = {
                    "user_id": thought.user_id,
                    "session_id": thought.session_id,
                    "agent_type": thought.agent_type,
                    "started_at": thought.timestamp,
                }
            
            # Add new thought
            thoughts.append(asdict(thought))
            
            # Keep only last 50 thoughts per conversation to prevent unbounded growth
            if len(thoughts) > 50:
                thoughts = thoughts[-50:]
            
            # Update trace data
            trace_data.update({
                "last_activity": thought.timestamp,
                "thoughts": thoughts,
                "total_thoughts": len(thoughts)
            })
            
            # Store with TTL (same as conversation state)
            ttl = self.redis_store._state_ttl or 2592000  # 30 days default
            self._redis.setex(trace_key, ttl, json.dumps(trace_data, ensure_ascii=False))
            
        except Exception as e:
            print(f"Warning: Failed to store thought: {e}")
    
    def get_conversation_trace(self, user_id: str, agent_type: str) -> Optional[ConversationTrace]:
        """Retrieve the complete conversation trace."""
        trace_key = self._trace_key(user_id, agent_type)
        
        try:
            data = self._redis.get(trace_key)
            if not data:
                return None
            
            trace_data = json.loads(data.decode('utf-8') if isinstance(data, bytes) else data)
            
            # Convert thoughts back to AgentThought objects
            thoughts = [AgentThought(**t) for t in trace_data.get("thoughts", [])]
            
            return ConversationTrace(
                user_id=trace_data["user_id"],
                session_id=trace_data["session_id"],
                agent_type=trace_data["agent_type"],
                started_at=trace_data["started_at"],
                last_activity=trace_data["last_activity"],
                thoughts=thoughts,
                total_thoughts=trace_data["total_thoughts"]
            )
            
        except Exception as e:
            print(f"Warning: Failed to retrieve trace for {user_id}:{agent_type}: {e}")
            return None
    
    def get_all_traces(self, limit: int = 100) -> List[ConversationTrace]:
        """Get all conversation traces."""
        traces = []
        
        try:
            # Get all trace keys
            pattern = f"{self._namespace}:trace:*"
            keys = self._redis.keys(pattern)
            
            for key in keys[:limit]:  # Limit to prevent memory issues
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                parts = key_str.split(':')
                
                if len(parts) >= 4:
                    user_id = parts[2]
                    agent_type = parts[3]
                    
                    trace = self.get_conversation_trace(user_id, agent_type)
                    if trace:
                        traces.append(trace)
            
            # Sort by last activity (most recent first)
            traces.sort(key=lambda t: t.last_activity, reverse=True)
            
        except Exception as e:
            print(f"Warning: Failed to retrieve all traces: {e}")
        
        return traces
    
    def clear_trace(self, user_id: str, agent_type: str) -> bool:
        """Clear a conversation trace."""
        trace_key = self._trace_key(user_id, agent_type)
        
        try:
            result = self._redis.delete(trace_key)
            return result > 0
        except Exception as e:
            print(f"Warning: Failed to clear trace for {user_id}:{agent_type}: {e}")
            return False
