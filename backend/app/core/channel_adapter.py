"""Channel-agnostic message processing for different communication channels.

This module provides a unified interface for processing messages that works
across CLI, WhatsApp, and any future channels while keeping the flow core pure.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.core.llm import LLMClient
    from app.services.tenant_config_service import ProjectContext

from app.core.naturalize import rewrite_whatsapp_multi


class ChannelAdapter(Protocol):
    """Protocol for channel-specific input/output handling."""

    def process_outbound(
        self,
        text: str,
        chat_history: list[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Process outbound message into channel-specific format.

        Returns list of messages with format: [{"text": str, "delay_ms": int, ...}]
        """

    def display_messages(
        self,
        messages: list[dict[str, Any]],
        prefix: str = "",
        debug_info: dict[str, Any] | None = None,
    ) -> None:
        """Display/send messages through the channel."""


class ConversationalRewriter:
    """Shared message rewriter that produces conversational multi-message output."""

    def __init__(self, llm: LLMClient | None = None) -> None:  # type: ignore[name-defined]
        self._llm = llm

    def rewrite_message(
        self,
        text: str,
        chat_history: list[dict[str, str]] | None = None,
        *,
        max_followups: int = 2,
        enable_rewrite: bool = True,
        project_context: ProjectContext | None = None,  # type: ignore[name-defined]
        is_completion: bool = False,
        tool_context: dict[str, str] | None = None,
        current_time: str | None = None,
    ) -> list[dict[str, Any]]:
        """Rewrite a message into conversational multi-message format.

        Args:
            text: Original message text
            chat_history: Recent conversation history
            max_followups: Maximum number of follow-up messages
            enable_rewrite: Whether to enable LLM rewriting
            is_completion: Whether this is the final message/completion of the conversation

        Returns:
            List of message dicts with keys: text, delay_ms
        """
        if not enable_rewrite or not self._llm or not text.strip():
            return [{"text": text, "delay_ms": 0}]

        try:
            return rewrite_whatsapp_multi(
                self._llm,
                text,
                chat_history,
                max_followups=max_followups,
                project_context=project_context,
                is_completion=is_completion,
                tool_context=tool_context,
                current_time=current_time,
            )
        except Exception:
            # Fallback to single message
            return [{"text": text, "delay_ms": 0}]

    def build_chat_history(
        self,
        langchain_history: Any = None,
        flow_context_history: list[Any] | None = None,
        latest_user_input: str | None = None,
    ) -> list[dict[str, str]]:
        """Build chat history from various sources."""
        import datetime
        
        chat_window: list[dict[str, str]] = []

        # From LangChain history (Redis/memory) - EXCLUDE current message being processed
        try:
            if langchain_history and hasattr(langchain_history, "messages"):
                messages = list(getattr(langchain_history, "messages", []))
                # Skip the last message if it matches the current user input (avoid including current message)
                if messages and latest_user_input:
                    last_msg = messages[-1]
                    last_content = getattr(last_msg, "content", "")
                    if last_content == latest_user_input:
                        messages = messages[:-1]  # Remove current message from history
                
                # CRITICAL: Also remove the last assistant message since that's what we're rewriting
                # We don't want the message being rewritten to appear in its own context
                if messages and len(messages) > 0:
                    last_msg = messages[-1]
                    last_role = getattr(last_msg, "type", None) or getattr(last_msg, "role", None)
                    if last_role in ["assistant", "ai"]:
                        messages = messages[:-1]  # Remove the assistant message being rewritten
                
                for m in messages:
                    role = getattr(m, "type", None) or getattr(m, "role", None) or "assistant"
                    content = getattr(m, "content", "")
                    if isinstance(content, list):
                        # Some models return list of content parts
                        content = " ".join(str(getattr(p, "text", p)) for p in content)
                    
                    # Add timestamp for better context
                    timestamp = datetime.datetime.now().strftime("%H:%M")
                    chat_window.append({
                        "role": str(role), 
                        "content": str(content),
                        "timestamp": timestamp
                    })
        except Exception:
            # ignore history extraction failures (non-fatal in adapters)
            pass

        # From flow context history - EXCLUDE current message AND last assistant message
        try:
            if flow_context_history:
                # Convert to list to allow indexing
                history_list = list(flow_context_history)
                
                # Remove the last assistant message since that's what we're rewriting
                if history_list and len(history_list) > 0:
                    last_turn = history_list[-1]
                    last_role = getattr(last_turn, "role", "assistant")
                    if last_role in ["assistant", "ai"]:
                        history_list = history_list[:-1]  # Remove the assistant message being rewritten
                
                for turn in history_list:
                    role = getattr(turn, "role", "assistant")
                    content = getattr(turn, "content", "")
                    
                    # Skip if this matches the current user input
                    if role == "user" and content == latest_user_input:
                        continue
                        
                    if role and content:
                        timestamp = datetime.datetime.now().strftime("%H:%M")
                        chat_window.append({
                            "role": str(role), 
                            "content": str(content),
                            "timestamp": timestamp
                        })
        except Exception:
            # ignore context extraction failures
            pass

        # DO NOT add latest_user_input to history - it's the current message being processed!

        return chat_window

    # (No post-processing; rely on LLM to manage transitions and wording.)


class CLIAdapter:
    """CLI channel adapter with optional delays and debug output."""

    def __init__(self, enable_delays: bool = True, debug_mode: bool = False) -> None:
        self.enable_delays = enable_delays
        self.debug_mode = debug_mode

    def process_outbound(
        self,
        text: str,
        chat_history: list[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """CLI just returns single message - rewriting handled by rewriter."""
        return [{"text": text, "delay_ms": 0}]

    def display_messages(
        self,
        messages: list[dict[str, Any]],
        prefix: str = "",
        debug_info: dict[str, Any] | None = None,
    ) -> None:
        """Display messages in CLI with optional delays."""
        if self.debug_mode and debug_info:
            debug_items = []
            for key, value in debug_info.items():
                if (isinstance(value, dict) and value) or (
                    isinstance(value, (list, tuple)) and value
                ):
                    debug_items.append(f"{key}={len(value)} items")
                else:
                    debug_items.append(f"{key}={value}")
            print(f"[DEBUG] {', '.join(debug_items)}")

        for i, msg in enumerate(messages):
            text = str(msg.get("text", "")).strip()
            if not text:
                continue

            if i > 0 and self.enable_delays:
                try:
                    delay_ms = int(msg.get("delay_ms", 800))
                    time.sleep(max(0, delay_ms) / 1000.0)
                except Exception:
                    time.sleep(0.8)

            print(f"{prefix}{text}")


class WhatsAppAdapter:
    """WhatsApp channel adapter that handles multi-message with delays."""

    def process_outbound(
        self,
        text: str,
        chat_history: list[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """WhatsApp returns the message plan as-is."""
        # This will be the rewritten plan from the rewriter
        return [{"text": text, "delay_ms": 0}]

    def send_followups(
        self,
        messages: list[dict[str, Any]],
        sender_callback: callable,  # type: ignore[name-defined]
    ) -> None:
        """Send follow-up messages using the provided callback."""
        for i, msg in enumerate(messages[1:], start=1):  # Skip first message
            try:
                text = str(msg.get("text", "")).strip()
                if not text:
                    continue
                delay_ms = int(msg.get("delay_ms", 800))
                time.sleep(max(0, delay_ms) / 1000.0)
                sender_callback(text)
            except Exception:
                continue
