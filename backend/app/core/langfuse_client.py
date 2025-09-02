"""Langfuse observability client for comprehensive LLM tracing."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator
from uuid import uuid4

from langfuse import Langfuse

if TYPE_CHECKING:
    from langfuse.client import StatefulSpanClient, StatefulTraceClient


class LangfuseObservability:
    """Centralized Langfuse client for LLM observability."""
    
    def __init__(self) -> None:
        """Initialize Langfuse client with environment variables."""
        self._client: Langfuse | None = None
        self._enabled = self._should_enable()
        
    def _should_enable(self) -> bool:
        """Check if Langfuse should be enabled based on environment variables."""
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        host = os.getenv("LANGFUSE_HOST")
        
        if not all([public_key, secret_key, host]):
            print("[LANGFUSE] Missing environment variables - observability disabled")
            return False
            
        return True
    
    @property
    def client(self) -> Langfuse | None:
        """Get or create Langfuse client."""
        if not self._enabled:
            return None
            
        if self._client is None:
            try:
                self._client = Langfuse()
                print("[LANGFUSE] Observability client initialized successfully")
            except Exception as e:
                print(f"[LANGFUSE] Failed to initialize client: {e}")
                self._enabled = False
                return None
                
        return self._client
    
    def is_enabled(self) -> bool:
        """Check if Langfuse observability is enabled."""
        return self._enabled and self.client is not None
    
    def create_trace(
        self,
        name: str,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> StatefulTraceClient | None:
        """Create a new trace for observability."""
        if not self.is_enabled():
            return None
            
        try:
            # Use the correct Langfuse v3 API
            trace = self.client.trace(  # type: ignore[union-attr]
                name=name,
                user_id=user_id,
                session_id=session_id,
                metadata=metadata or {},
                tags=tags or [],
            )
            return trace
        except AttributeError:
            # Fallback for older Langfuse versions
            try:
                trace = self.client.create_trace(  # type: ignore[union-attr]
                    name=name,
                    user_id=user_id,
                    session_id=session_id,
                    metadata=metadata or {},
                    tags=tags or [],
                )
                return trace
            except Exception as e:
                print(f"[LANGFUSE] Failed to create trace with fallback: {e}")
                return None
        except Exception as e:
            print(f"[LANGFUSE] Failed to create trace: {e}")
            return None
    
    @contextmanager
    def trace_context(
        self,
        name: str,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Generator[StatefulTraceClient | None, None, None]:
        """Context manager for tracing operations."""
        trace = self.create_trace(
            name=name,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
            tags=tags,
        )
        
        try:
            yield trace
        finally:
            if trace and self.is_enabled():
                try:
                    self.client.flush()  # type: ignore[union-attr]
                except Exception as e:
                    print(f"[LANGFUSE] Failed to flush trace: {e}")
    
    def flush(self) -> None:
        """Flush all pending observations to Langfuse."""
        if self.is_enabled():
            try:
                self.client.flush()  # type: ignore[union-attr]
            except Exception as e:
                print(f"[LANGFUSE] Failed to flush: {e}")


# Global instance
_langfuse_client: LangfuseObservability | None = None


def get_langfuse_client() -> LangfuseObservability:
    """Get the global Langfuse observability client."""
    global _langfuse_client
    if _langfuse_client is None:
        _langfuse_client = LangfuseObservability()
    return _langfuse_client


def trace_llm_call(
    name: str,
    model: str,
    input_text: str,
    output_text: str,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    trace: StatefulTraceClient | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> StatefulSpanClient | None:
    """
    Trace an LLM call with comprehensive metadata.
    
    Args:
        name: Name of the LLM operation
        model: Model name used
        input_text: Input prompt/text
        output_text: LLM response
        metadata: Additional metadata
        tags: Tags for categorization
        trace: Parent trace (if None, creates a new one)
        user_id: User identifier
        session_id: Session identifier
    
    Returns:
        Span client for further operations
    """
    client = get_langfuse_client()
    if not client.is_enabled():
        return None
    
    try:
        # Create trace if not provided
        if trace is None:
            trace = client.create_trace(
                name=f"llm_call_{name}",
                user_id=user_id,
                session_id=session_id,
                metadata=metadata,
                tags=tags,
            )
        
        if trace is None:
            return None
        
        # Create generation span for LLM call
        generation = trace.generation(
            name=name,
            model=model,
            input=input_text,
            output=output_text,
            metadata=metadata or {},
            tags=tags or [],
        )
        
        return generation
        
    except Exception as e:
        print(f"[LANGFUSE] Failed to trace LLM call: {e}")
        return None


def trace_tool_call(
    name: str,
    input_data: dict[str, Any],
    output_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    trace: StatefulTraceClient | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> StatefulSpanClient | None:
    """
    Trace a tool call operation.
    
    Args:
        name: Name of the tool operation
        input_data: Tool input parameters
        output_data: Tool output/result
        metadata: Additional metadata
        tags: Tags for categorization
        trace: Parent trace (if None, creates a new one)
        user_id: User identifier
        session_id: Session identifier
    
    Returns:
        Span client for further operations
    """
    client = get_langfuse_client()
    if not client.is_enabled():
        return None
    
    try:
        # Create trace if not provided
        if trace is None:
            trace = client.create_trace(
                name=f"tool_call_{name}",
                user_id=user_id,
                session_id=session_id,
                metadata=metadata,
                tags=tags,
            )
        
        if trace is None:
            return None
        
        # Create span for tool call
        span = trace.span(
            name=name,
            input=input_data,
            output=output_data,
            metadata=metadata or {},
            tags=tags or [],
        )
        
        return span
        
    except Exception as e:
        print(f"[LANGFUSE] Failed to trace tool call: {e}")
        return None
