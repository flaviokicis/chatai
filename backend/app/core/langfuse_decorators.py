"""Clean decorators and context managers for Langfuse observability."""

from __future__ import annotations

import functools
import json
from contextlib import contextmanager
from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Any, TypeVar

from .langfuse_client import get_langfuse_client

if TYPE_CHECKING:
    from langfuse.client import StatefulTraceClient

F = TypeVar("F", bound=Callable[..., Any])


class LangfuseTracer:
    """Clean, minimal interface for LLM observability."""
    
    def __init__(self) -> None:
        self._client = get_langfuse_client()
    
    @contextmanager
    def trace_llm_operation(
        self,
        operation_name: str,
        model_name: str | None = None,
        **context_data: Any,
    ) -> Generator[LLMTraceContext, None, None]:
        """Context manager for tracing LLM operations with minimal setup."""
        if not self._client.is_enabled():
            yield LLMTraceContext(None, operation_name, model_name)
            return
        
        # Extract common context
        user_id = context_data.get("user_id")
        session_id = context_data.get("session_id") 
        flow_id = context_data.get("flow_id")
        
        trace = self._client.create_trace(
            name=operation_name,
            user_id=str(user_id) if user_id else None,
            session_id=str(session_id) if session_id else None,
            metadata={
                "operation": operation_name,
                "model": model_name or "unknown",
                **{k: v for k, v in context_data.items() if k not in ("user_id", "session_id", "flow_id")},
            },
            tags=[
                operation_name,
                model_name or "unknown",
                "llm_operation",
            ],
        )
        
        try:
            yield LLMTraceContext(trace, operation_name, model_name)
        finally:
            if trace:
                self._client.flush()


class LLMTraceContext:
    """Simplified context for LLM tracing operations."""
    
    def __init__(self, trace: StatefulTraceClient | None, operation_name: str, model_name: str | None):
        self.trace = trace
        self.operation_name = operation_name
        self.model_name = model_name or "unknown"
    
    def log_llm_call(self, input_text: str, output_text: str, **metadata: Any) -> None:
        """Log an LLM generation call."""
        if not self.trace:
            return
            
        self.trace.generation(
            name=f"{self.operation_name}_llm",
            model=self.model_name,
            input=input_text,
            output=output_text,
            metadata=metadata,
            tags=["llm_call"],
        )
    
    def log_tool_selection(self, tools: list[str], selected_tool: str, **metadata: Any) -> None:
        """Log tool selection process."""
        if not self.trace:
            return
            
        self.trace.span(
            name="tool_selection",
            input={"available_tools": tools},
            output={"selected_tool": selected_tool},
            metadata={"tools_count": len(tools), **metadata},
            tags=["tool_selection"],
        )
    
    def log_error(self, error: Exception, context: dict[str, Any] | None = None) -> None:
        """Log an error during the operation."""
        if not self.trace:
            return
            
        self.trace.event(
            name="operation_error",
            input=context or {},
            output={"error": str(error), "error_type": type(error).__name__},
            metadata={"fallback_used": True},
        )
    
    def log_result(self, result: Any, **metadata: Any) -> None:
        """Log the final result of the operation."""
        if not self.trace:
            return
            
        self.trace.span(
            name="operation_result",
            input={},
            output={"result": str(result)[:1000]},  # Truncate long results
            metadata=metadata,
            tags=["result"],
        )


# Global tracer instance
_tracer = LangfuseTracer()


def trace_llm_method(
    operation_name: str | None = None,
    extract_context: Callable[[Any, tuple[Any, ...], dict[str, Any]], dict[str, Any]] | None = None,
) -> Callable[[F], F]:
    """
    Decorator for tracing LLM method calls with minimal code intrusion.
    
    Args:
        operation_name: Name of the operation (defaults to method name)
        extract_context: Function to extract context from method args
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            op_name = operation_name or f"{self.__class__.__name__}_{func.__name__}"
            model_name = getattr(self, "model_name", None) or getattr(getattr(self, "_llm", None), "model_name", None)
            
            # Extract context if function provided
            context = {}
            if extract_context:
                try:
                    context = extract_context(self, args, kwargs)
                except Exception:
                    pass  # Don't fail if context extraction fails
            
            with _tracer.trace_llm_operation(op_name, model_name, **context) as trace_ctx:
                try:
                    result = func(self, *args, **kwargs)
                    
                    # Auto-log common patterns
                    if hasattr(result, "get") and "__tool_name__" in result:
                        # Tool calling result
                        tools = kwargs.get("tools", []) or (args[1] if len(args) > 1 else [])
                        tool_names = [getattr(t, "__name__", str(t)) for t in tools] if tools else []
                        selected_tool = result.get("__tool_name__", "unknown")
                        
                        trace_ctx.log_llm_call(
                            input_text=str(args[0])[:500] if args else "",
                            output_text=json.dumps(result, ensure_ascii=False)[:500],
                            selected_tool=selected_tool,
                        )
                        
                        if tool_names:
                            trace_ctx.log_tool_selection(tool_names, selected_tool)
                    
                    elif isinstance(result, str):
                        # Text generation result
                        trace_ctx.log_llm_call(
                            input_text=str(args[0])[:500] if args else "",
                            output_text=result[:500],
                        )
                    
                    return result
                    
                except Exception as e:
                    trace_ctx.log_error(e, {"args": str(args)[:200], "kwargs": str(kwargs)[:200]})
                    raise
                    
        return wrapper  # type: ignore
    return decorator


@contextmanager
def trace_flow_operation(
    operation_name: str,
    ctx: Any = None,
    **extra_context: Any,
) -> Generator[LLMTraceContext, None, None]:
    """Context manager for tracing flow operations with automatic context extraction."""
    context = {}
    
    # Extract common flow context
    if ctx:
        context.update({
            "user_id": getattr(ctx, "user_id", None),
            "session_id": getattr(ctx, "session_id", None),
            "flow_id": getattr(ctx, "flow_id", None),
            "tenant_id": getattr(ctx, "tenant_id", None),
            "active_path": getattr(ctx, "active_path", None),
            "conversation_style": getattr(ctx, "conversation_style", None),
            "clarification_count": getattr(ctx, "clarification_count", 0),
            "answers_collected": len(getattr(ctx, "answers", {})),
        })
    
    context.update(extra_context)
    
    with _tracer.trace_llm_operation(operation_name, **context) as trace_ctx:
        yield trace_ctx


# Convenience functions for common patterns
def trace_tool_calling(ctx: Any = None, **extra: Any) -> Any:
    """Trace a tool calling operation."""
    return trace_flow_operation("tool_calling", ctx, **extra)


def trace_text_rewrite(style: str = "default", **extra: Any) -> Any:
    """Trace a text rewriting operation."""
    return trace_flow_operation("text_rewrite", style=style, **extra)


def trace_flow_decision(decision_type: str, **extra: Any) -> Any:
    """Trace a flow decision operation."""
    return trace_flow_operation(f"flow_{decision_type}", **extra)
