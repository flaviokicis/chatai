"""Clean Langfuse observability using the official v3 OpenTelemetry-based SDK."""

from __future__ import annotations

import functools
import json
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Generator, TypeVar

from langfuse import get_client, observe

if TYPE_CHECKING:
    from langfuse.client import LangfuseClient

F = TypeVar("F", bound=Callable[..., Any])


def get_langfuse() -> LangfuseClient:
    """Get the Langfuse client."""
    return get_client()


def is_langfuse_enabled() -> bool:
    """Check if Langfuse is enabled via environment variables."""
    return all([
        os.getenv("LANGFUSE_PUBLIC_KEY"),
        os.getenv("LANGFUSE_SECRET_KEY"), 
        os.getenv("LANGFUSE_HOST"),
    ])


def trace_llm_method(
    operation_name: str | None = None,
    capture_input: bool = True,
    capture_output: bool = True,
) -> Callable[[F], F]:
    """
    Clean decorator for tracing LLM methods using official Langfuse v3 API.
    
    Uses the @observe decorator from Langfuse SDK for automatic tracing.
    """
    def decorator(func: F) -> F:
        # Use Langfuse's official @observe decorator
        observed_func = observe(name=operation_name or func.__name__)(func)
        
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # The @observe decorator handles all the tracing automatically
            return observed_func(*args, **kwargs)
            
        return wrapper  # type: ignore
    return decorator


@contextmanager
def trace_operation(
    name: str,
    metadata: dict[str, Any] | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> Generator[Any, None, None]:
    """
    Context manager for tracing operations using Langfuse v3 context managers.
    
    Based on the official documentation example.
    """
    if not is_langfuse_enabled():
        yield None
        return
    
    langfuse = get_langfuse()
    
    # Use the official Langfuse context manager approach
    with langfuse.start_as_current_span(name=name) as span:
        # Add metadata if provided
        if metadata:
            span.update(metadata=metadata)
        
        # Set user context if provided
        if user_id or session_id:
            span.update(
                user_id=user_id,
                session_id=session_id,
            )
        
        yield span


@contextmanager 
def trace_generation(
    name: str,
    model: str,
    input_text: str | None = None,
    metadata: dict[str, Any] | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> Generator[Any, None, None]:
    """
    Context manager for tracing LLM generations using Langfuse v3.
    
    Based on the official documentation for generation tracing.
    """
    if not is_langfuse_enabled():
        yield None
        return
    
    langfuse = get_langfuse()
    
    # Use the official Langfuse generation context manager
    with langfuse.start_as_current_generation(name=name, model=model) as generation:
        # Set input if provided
        if input_text:
            generation.update(input=input_text)
        
        # Add metadata if provided
        if metadata:
            generation.update(metadata=metadata)
        
        # Set user context if provided
        if user_id or session_id:
            generation.update(
                user_id=user_id,
                session_id=session_id,
            )
        
        yield generation


# Convenience functions for common patterns
def trace_tool_calling(
    ctx: Any = None,
    **extra_metadata: Any,
) -> Any:
    """Trace a tool calling operation with flow context."""
    metadata = {"operation": "tool_calling", **extra_metadata}
    
    # Extract context information if available
    user_id = getattr(ctx, "user_id", None) if ctx else None
    session_id = getattr(ctx, "session_id", None) if ctx else None
    
    if ctx:
        metadata.update({
            "flow_id": getattr(ctx, "flow_id", None),
            "tenant_id": getattr(ctx, "tenant_id", None),
            "active_path": getattr(ctx, "active_path", None),
            "conversation_style": getattr(ctx, "conversation_style", None),
            "clarification_count": getattr(ctx, "clarification_count", 0),
            "answers_collected": len(getattr(ctx, "answers", {})),
        })
    
    return trace_operation(
        name="tool_calling",
        metadata=metadata,
        user_id=str(user_id) if user_id else None,
        session_id=str(session_id) if session_id else None,
    )


def trace_text_rewrite(
    style: str = "default",
    model: str = "gemini-2.5-flash-lite",
    **extra_metadata: Any,
) -> Any:
    """Trace a text rewriting/naturalization operation."""
    metadata = {
        "operation": "text_rewriting",
        "style": style,
        **extra_metadata,
    }
    
    return trace_generation(
        name="text_naturalization",
        model=model,
        metadata=metadata,
    )


def trace_flow_decision(
    decision_type: str,
    model: str = "gemini-2.5-flash",
    **extra_metadata: Any,
) -> Any:
    """Trace a flow decision operation."""
    metadata = {
        "operation": f"flow_{decision_type}",
        "decision_type": decision_type,
        **extra_metadata,
    }
    
    return trace_generation(
        name=f"flow_{decision_type}",
        model=model,
        metadata=metadata,
    )


# Helper class for manual tracing when decorators aren't suitable
class LangfuseTracer:
    """Manual tracer for complex scenarios."""
    
    def __init__(self) -> None:
        self._client = get_langfuse()
        self._enabled = is_langfuse_enabled()
    
    def is_enabled(self) -> bool:
        """Check if tracing is enabled."""
        return self._enabled
    
    def trace_llm_call(
        self,
        name: str,
        model: str,
        input_text: str,
        output_text: str,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Trace a completed LLM call."""
        if not self.is_enabled():
            return
        
        # Use the new start_observation API with correct parameters
        observation = self._client.start_observation(
            name=name,
            as_type="generation",
            model=model,
            input=input_text,
            output=output_text,
            metadata={
                **(metadata or {}),
                "user_id": user_id,
                "session_id": session_id,
            },
        )
        
        # End the observation
        observation.end()
    
    def flush(self) -> None:
        """Flush pending traces."""
        if self.is_enabled():
            self._client.flush()


# Global tracer instance
_tracer = LangfuseTracer()


def get_tracer() -> LangfuseTracer:
    """Get the global tracer instance."""
    return _tracer
