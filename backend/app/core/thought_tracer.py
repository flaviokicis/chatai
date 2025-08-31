"""
Database-backed thought tracing system for capturing and storing agent reasoning and decision-making processes.

This module provides functionality to:
- Capture agent thoughts, tool selections, and reasoning
- Store traces persistently in the database with proper GDPR/LGPD encryption
- Retrieve traces for debugging and analysis with proper tenant isolation
- Automatic cleanup of old traces to manage storage
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func

from app.db.models import AgentConversationTrace, AgentThought, Tenant


@dataclass
class AgentThoughtData:
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
    extra_metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_metadata is None:
            self.extra_metadata = {}


@dataclass
class ConversationTraceData:
    """Represents a complete conversation trace with all thoughts."""
    
    user_id: str
    session_id: str
    agent_type: str
    tenant_id: str
    started_at: str
    last_activity: str
    thoughts: List[AgentThoughtData]
    total_thoughts: int


class DatabaseThoughtTracer:
    """Database-backed thought tracing for agent interactions with persistent storage."""
    
    def __init__(self, session: Session):
        """
        Initialize the thought tracer with a database session.
        
        Args:
            session: SQLAlchemy session for database operations
        """
        self.session = session
        self._pending_thoughts: Dict[str, Dict[str, Any]] = {}
    
    def start_thought(
        self,
        user_id: str,
        session_id: str,
        agent_type: str,
        user_message: str,
        current_state: Dict[str, Any],
        available_tools: List[str],
        tenant_id: UUID,
        model_name: str = "unknown"
    ) -> str:
        """Start a new thought process and return thought ID."""
        thought_id = str(uuid4())
        
        # Store pending thought data
        self._pending_thoughts[thought_id] = {
            "user_id": user_id,
            "session_id": session_id,
            "agent_type": agent_type,
            "user_message": user_message,
            "current_state": current_state,
            "available_tools": available_tools,
            "tenant_id": tenant_id,
            "model_name": model_name,
            "start_time": time.time(),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        
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
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Complete a thought with reasoning and results."""
        if thought_id not in self._pending_thoughts:
            # Thought expired or doesn't exist, skip silently
            return
        
        try:
            pending_data = self._pending_thoughts.pop(thought_id)
            
            # Calculate processing time
            processing_time_ms = None
            if "start_time" in pending_data:
                processing_time_ms = int((time.time() - pending_data["start_time"]) * 1000)
            
            # Get or create conversation trace
            trace = self._get_or_create_conversation_trace(
                tenant_id=pending_data["tenant_id"],
                user_id=pending_data["user_id"],
                session_id=pending_data["session_id"],
                agent_type=pending_data["agent_type"]
            )
            
            # Create the thought record
            thought = AgentThought(
                conversation_trace_id=trace.id,
                user_message=pending_data["user_message"],
                current_state=pending_data["current_state"],
                available_tools=pending_data["available_tools"],
                reasoning=reasoning,
                selected_tool=selected_tool,
                tool_args=tool_args,
                confidence=confidence,
                tool_result=tool_result,
                agent_response=agent_response,
                errors=errors,
                processing_time_ms=processing_time_ms,
                model_name=pending_data["model_name"],
                extra_metadata=extra_metadata or {}
            )
            
            self.session.add(thought)
            
            # Update trace metadata
            trace.last_activity_at = datetime.now(UTC)
            # Increment counter atomically
            trace.total_thoughts = (trace.total_thoughts or 0) + 1
            
            # Commit the transaction
            self.session.commit()
            
            # Clean up old thoughts to prevent unbounded growth
            self._cleanup_old_thoughts(trace)
            
        except Exception as e:
            # Rollback on error and log warning
            self.session.rollback()
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Failed to store thought %s: %s", thought_id, e)
    
    def _get_or_create_conversation_trace(
        self, 
        tenant_id: UUID, 
        user_id: str, 
        session_id: str, 
        agent_type: str
    ) -> AgentConversationTrace:
        """Get existing conversation trace or create a new one."""
        # Try to find existing trace
        trace = self.session.query(AgentConversationTrace).filter(
            and_(
                AgentConversationTrace.tenant_id == tenant_id,
                AgentConversationTrace.user_id == user_id,
                AgentConversationTrace.agent_type == agent_type
            )
        ).first()
        
        if trace is None:
            # Create new trace
            now = datetime.now(UTC)
            trace = AgentConversationTrace(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                agent_type=agent_type,
                started_at=now,
                last_activity_at=now,
                total_thoughts=0
            )
            self.session.add(trace)
            self.session.flush()  # Get the ID
        
        return trace
    
    def _cleanup_old_thoughts(self, trace: AgentConversationTrace) -> None:
        """Remove old thoughts to keep storage manageable (keep last 100 per conversation)."""
        try:
            # Count current thoughts
            thought_count = self.session.query(func.count(AgentThought.id)).filter(
                AgentThought.conversation_trace_id == trace.id
            ).scalar()
            
            if thought_count > 100:
                # Get IDs of thoughts to delete (keep last 100)
                thoughts_to_delete = self.session.query(AgentThought.id).filter(
                    AgentThought.conversation_trace_id == trace.id
                ).order_by(desc(AgentThought.created_at)).offset(100).all()
                
                if thoughts_to_delete:
                    thought_ids = [t.id for t in thoughts_to_delete]
                    self.session.query(AgentThought).filter(
                        AgentThought.id.in_(thought_ids)
                    ).delete(synchronize_session=False)
                    
                    # Update thought count
                    trace.total_thoughts = 100
                    
                    self.session.commit()
                    
        except Exception as e:
            # Don't fail the main operation if cleanup fails
            self.session.rollback()
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Failed to cleanup old thoughts for trace %s: %s", trace.id, e)
    
    def get_conversation_trace(self, tenant_id: UUID, user_id: str, agent_type: str) -> Optional[ConversationTraceData]:
        """Retrieve the complete conversation trace for a specific user and agent type."""
        try:
            # Get the trace with all thoughts
            trace = self.session.query(AgentConversationTrace).filter(
                and_(
                    AgentConversationTrace.tenant_id == tenant_id,
                    AgentConversationTrace.user_id == user_id,
                    AgentConversationTrace.agent_type == agent_type
                )
            ).first()
            
            if not trace:
                return None
            
            # Get all thoughts for this trace, ordered by creation time
            thoughts = self.session.query(AgentThought).filter(
                AgentThought.conversation_trace_id == trace.id
            ).order_by(AgentThought.created_at).all()
            
            # Convert to data objects
            thought_data = []
            for thought in thoughts:
                thought_data.append(AgentThoughtData(
                    id=str(thought.id),
                    timestamp=thought.created_at.isoformat(),
                    user_id=trace.user_id,
                    session_id=trace.session_id or "unknown",
                    agent_type=trace.agent_type,
                    user_message=thought.user_message,
                    current_state=thought.current_state or {},
                    available_tools=thought.available_tools or [],
                    reasoning=thought.reasoning,
                    selected_tool=thought.selected_tool,
                    tool_args=thought.tool_args or {},
                    confidence=thought.confidence,
                    tool_result=thought.tool_result,
                    agent_response=thought.agent_response,
                    errors=thought.errors,
                    model_name=thought.model_name,
                    processing_time_ms=thought.processing_time_ms,
                    extra_metadata=thought.extra_metadata or {}
                ))
            
            return ConversationTraceData(
                user_id=trace.user_id,
                session_id=trace.session_id or "unknown",
                agent_type=trace.agent_type,
                tenant_id=str(trace.tenant_id),
                started_at=trace.started_at.isoformat(),
                last_activity=trace.last_activity_at.isoformat(),
                thoughts=thought_data,
                total_thoughts=trace.total_thoughts
            )
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Failed to retrieve trace for %s:%s: %s", user_id, agent_type, e)
            return None
    
    def get_all_traces(self, tenant_id: UUID, limit: int = 100, active_only: bool = False) -> List[ConversationTraceData]:
        """Get all conversation traces for a tenant."""
        try:
            query = self.session.query(AgentConversationTrace).filter(
                AgentConversationTrace.tenant_id == tenant_id
            )
            
            # Filter for active conversations (last 24 hours) if requested
            if active_only:
                cutoff = datetime.now(UTC) - timedelta(hours=24)
                query = query.filter(AgentConversationTrace.last_activity_at >= cutoff)
            
            # Order by last activity and limit
            traces = query.order_by(desc(AgentConversationTrace.last_activity_at)).limit(limit).all()
            
            result = []
            for trace in traces:
                # Get recent thoughts (last 10 for performance)
                recent_thoughts = self.session.query(AgentThought).filter(
                    AgentThought.conversation_trace_id == trace.id
                ).order_by(desc(AgentThought.created_at)).limit(10).all()
                
                # Convert to data objects
                thought_data = []
                for thought in reversed(recent_thoughts):  # Reverse to chronological order
                    thought_data.append(AgentThoughtData(
                        id=str(thought.id),
                        timestamp=thought.created_at.isoformat(),
                        user_id=trace.user_id,
                        session_id=trace.session_id or "unknown",
                        agent_type=trace.agent_type,
                        user_message=thought.user_message,
                        current_state=thought.current_state or {},
                        available_tools=thought.available_tools or [],
                        reasoning=thought.reasoning,
                        selected_tool=thought.selected_tool,
                        tool_args=thought.tool_args or {},
                        confidence=thought.confidence,
                        tool_result=thought.tool_result,
                        agent_response=thought.agent_response,
                        errors=thought.errors,
                        model_name=thought.model_name,
                        processing_time_ms=thought.processing_time_ms,
                        extra_metadata=thought.extra_metadata or {}
                    ))
                
                result.append(ConversationTraceData(
                    user_id=trace.user_id,
                    session_id=trace.session_id or "unknown",
                    agent_type=trace.agent_type,
                    tenant_id=str(trace.tenant_id),
                    started_at=trace.started_at.isoformat(),
                    last_activity=trace.last_activity_at.isoformat(),
                    thoughts=thought_data,
                    total_thoughts=trace.total_thoughts
                ))
            
            return result
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Failed to retrieve all traces for tenant %s: %s", tenant_id, e)
            return []
    
    def clear_trace(self, tenant_id: UUID, user_id: str, agent_type: str) -> bool:
        """Clear a conversation trace and all its thoughts."""
        try:
            # Find the trace
            trace = self.session.query(AgentConversationTrace).filter(
                and_(
                    AgentConversationTrace.tenant_id == tenant_id,
                    AgentConversationTrace.user_id == user_id,
                    AgentConversationTrace.agent_type == agent_type
                )
            ).first()
            
            if not trace:
                return False
            
            # Delete the trace (cascade will delete thoughts)
            self.session.delete(trace)
            self.session.commit()
            
            return True
            
        except Exception as e:
            self.session.rollback()
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Failed to clear trace for %s:%s: %s", user_id, agent_type, e)
            return False
    
    def cleanup_old_traces(self, tenant_id: UUID, days_to_keep: int = 30) -> int:
        """Clean up old conversation traces to manage storage."""
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=days_to_keep)
            
            # Delete old traces (cascade will delete thoughts)
            deleted_count = self.session.query(AgentConversationTrace).filter(
                and_(
                    AgentConversationTrace.tenant_id == tenant_id,
                    AgentConversationTrace.last_activity_at < cutoff_date
                )
            ).delete()
            
            self.session.commit()
            return deleted_count
            
        except Exception as e:
            self.session.rollback()
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Failed to cleanup old traces for tenant %s: %s", tenant_id, e)
            return 0


# Backward compatibility alias
ThoughtTracer = DatabaseThoughtTracer