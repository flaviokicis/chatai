"""Langfuse v3 observability client using the correct OpenTelemetry-based API."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

from langfuse import Langfuse

if TYPE_CHECKING:
    from langfuse.client import StatefulSpanClient, StatefulTraceClient


class LangfuseObservabilityV3:
    """Langfuse v3 client using the correct OpenTelemetry-based API."""
    
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
                self._client = Langfuse(
                    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                    host=os.getenv("LANGFUSE_HOST"),
                )
                print("[LANGFUSE] v3 client initialized successfully")
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
    ) -> str | None:
        """Create a new trace and return trace ID."""
        if not self.is_enabled():
            return None
            
        try:
            # In Langfuse v3, we create traces using the event-based API
            trace_id = self.client.create_trace_id()  # type: ignore[union-attr]
            
            # Create the initial trace event
            self.client.event(  # type: ignore[union-attr]
                name=name,
                trace_id=trace_id,
                metadata=metadata or {},
                user_id=user_id,
                session_id=session_id,
                tags=tags or [],
            )
            
            return trace_id
        except Exception as e:
            print(f"[LANGFUSE] Failed to create trace: {e}")
            return None
    
    def create_generation(
        self,
        name: str,
        model: str,
        input_text: str,
        output_text: str,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Create a generation event."""
        if not self.is_enabled():
            return
            
        try:
            self.client.generation(  # type: ignore[union-attr]
                name=name,
                model=model,
                input=input_text,
                output=output_text,
                trace_id=trace_id,
                metadata=metadata or {},
                tags=tags or [],
            )
        except Exception as e:
            print(f"[LANGFUSE] Failed to create generation: {e}")
    
    def create_span(
        self,
        name: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Create a span event."""
        if not self.is_enabled():
            return
            
        try:
            self.client.span(  # type: ignore[union-attr]
                name=name,
                input=input_data or {},
                output=output_data or {},
                trace_id=trace_id,
                metadata=metadata or {},
                tags=tags or [],
            )
        except Exception as e:
            print(f"[LANGFUSE] Failed to create span: {e}")
    
    def create_event(
        self,
        name: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create an event."""
        if not self.is_enabled():
            return
            
        try:
            self.client.event(  # type: ignore[union-attr]
                name=name,
                input=input_data or {},
                output=output_data or {},
                trace_id=trace_id,
                metadata=metadata or {},
            )
        except Exception as e:
            print(f"[LANGFUSE] Failed to create event: {e}")
    
    def flush(self) -> None:
        """Flush all pending observations to Langfuse."""
        if self.is_enabled():
            try:
                self.client.flush()  # type: ignore[union-attr]
            except Exception as e:
                print(f"[LANGFUSE] Failed to flush: {e}")


# Global instance
_langfuse_client_v3: LangfuseObservabilityV3 | None = None


def get_langfuse_client_v3() -> LangfuseObservabilityV3:
    """Get the global Langfuse v3 observability client."""
    global _langfuse_client_v3
    if _langfuse_client_v3 is None:
        _langfuse_client_v3 = LangfuseObservabilityV3()
    return _langfuse_client_v3


def trace_llm_call_v3(
    name: str,
    model: str,
    input_text: str,
    output_text: str,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> str | None:
    """
    Trace an LLM call with the v3 API.
    
    Returns the trace ID for further operations.
    """
    client = get_langfuse_client_v3()
    if not client.is_enabled():
        return None
    
    try:
        # Create trace
        trace_id = client.create_trace(
            name=f"llm_call_{name}",
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
            tags=tags,
        )
        
        if trace_id:
            # Create generation
            client.create_generation(
                name=name,
                model=model,
                input_text=input_text,
                output_text=output_text,
                trace_id=trace_id,
                metadata=metadata,
                tags=tags,
            )
        
        return trace_id
        
    except Exception as e:
        print(f"[LANGFUSE] Failed to trace LLM call: {e}")
        return None


@contextmanager
def trace_operation_v3(
    name: str,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> Generator[str | None, None, None]:
    """Context manager for tracing operations with v3 API."""
    client = get_langfuse_client_v3()
    
    if not client.is_enabled():
        yield None
        return
    
    trace_id = client.create_trace(
        name=name,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
        tags=tags,
    )
    
    try:
        yield trace_id
    finally:
        if trace_id:
            client.flush()
