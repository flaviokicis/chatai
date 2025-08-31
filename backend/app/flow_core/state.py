"""Flow state management with proper persistence and context tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


class NodeStatus(str, Enum):
    """Status of a node in the flow."""

    NOT_VISITED = "not_visited"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True)
class ConversationTurn:
    """Represents a single turn in the conversation."""

    timestamp: datetime
    role: Literal["user", "assistant", "system"]
    content: str
    node_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NodeState:
    """State of a single node in the flow."""

    node_id: str
    status: NodeStatus = NodeStatus.NOT_VISITED
    visits: int = 0
    last_visited: datetime | None = None
    validation_errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FlowContext:
    """Rich context for LLM-aware decision making."""

    # Core state
    flow_id: str
    current_node_id: str | None = None
    answers: dict[str, Any] = field(default_factory=dict)

    # Session info (for thought tracing)
    user_id: str | None = None
    session_id: str | None = None
    tenant_id: Any | None = None  # UUID, but avoiding import cycle

    # Node tracking
    node_states: dict[str, NodeState] = field(default_factory=dict)
    pending_field: str | None = None

    # Conversation history
    history: list[ConversationTurn] = field(default_factory=list)
    turn_count: int = 0

    # Path management (for multi-path flows)
    available_paths: list[str] = field(default_factory=list)
    active_path: str | None = None
    path_confidence: dict[str, float] = field(default_factory=dict)
    path_locked: bool = False
    path_labels: dict[str, str] = field(default_factory=dict)  # Maps path keys to human-readable labels
    path_corrections: int = 0  # Track how many times user has corrected path

    # LLM context hints
    user_intent: str | None = None
    conversation_style: str | None = None  # formal, casual, technical, etc.
    clarification_count: int = 0

    # Flow control
    is_complete: bool = False
    escalation_reason: str | None = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    session_id: str | None = None

    def add_turn(
        self,
        role: Literal["user", "assistant", "system"],
        content: str,
        node_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a conversation turn to history."""
        turn = ConversationTurn(
            timestamp=datetime.now(),
            role=role,
            content=content,
            node_id=node_id,
            metadata=metadata or {},
        )
        self.history.append(turn)
        self.turn_count += 1
        self.updated_at = datetime.now()

    def get_node_state(self, node_id: str) -> NodeState:
        """Get or create node state."""
        if node_id not in self.node_states:
            self.node_states[node_id] = NodeState(node_id=node_id)
        return self.node_states[node_id]

    def mark_node_visited(self, node_id: str, status: NodeStatus = NodeStatus.IN_PROGRESS) -> None:
        """Mark a node as visited."""
        state = self.get_node_state(node_id)
        state.status = status
        state.visits += 1
        state.last_visited = datetime.now()
        self.current_node_id = node_id
        self.updated_at = datetime.now()

    def get_recent_history(self, limit: int = 10) -> list[dict[str, str]]:
        """Get recent conversation history for LLM context."""
        recent = self.history[-limit:] if len(self.history) > limit else self.history
        return [
            {
                "role": turn.role,
                "content": turn.content,
                "timestamp": turn.timestamp.isoformat(),
            }
            for turn in recent
        ]

    def update_last_assistant_message(self, new_content: str) -> None:
        """Update the content of the last assistant message with rewritten version."""
        # Find the last assistant message and update its content
        for i in range(len(self.history) - 1, -1, -1):
            if self.history[i].role == "assistant":
                self.history[i].content = new_content
                self.updated_at = datetime.now()
                break

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for persistence."""
        return {
            "flow_id": self.flow_id,
            "current_node_id": self.current_node_id,
            "answers": self.answers,
            "node_states": {
                nid: {
                    "status": state.status,
                    "visits": state.visits,
                    "last_visited": state.last_visited.isoformat() if state.last_visited else None,
                    "validation_errors": state.validation_errors,
                    "metadata": state.metadata,
                }
                for nid, state in self.node_states.items()
            },
            "history": [
                {
                    "timestamp": turn.timestamp.isoformat(),
                    "role": turn.role,
                    "content": turn.content,
                    "node_id": turn.node_id,
                    "metadata": turn.metadata,
                }
                for turn in self.history
            ],
            "turn_count": self.turn_count,
            "available_paths": self.available_paths,
            "active_path": self.active_path,
            "path_confidence": self.path_confidence,
            "path_locked": self.path_locked,
            "user_intent": self.user_intent,
            "conversation_style": self.conversation_style,
            "clarification_count": self.clarification_count,
            "is_complete": self.is_complete,
            "escalation_reason": self.escalation_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "session_id": self.session_id,
            "pending_field": self.pending_field,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlowContext:
        """Deserialize from dict."""
        ctx = cls(
            flow_id=data["flow_id"],
            current_node_id=data.get("current_node_id"),
            answers=data.get("answers", {}),
            turn_count=data.get("turn_count", 0),
            available_paths=data.get("available_paths", []),
            active_path=data.get("active_path"),
            path_confidence=data.get("path_confidence", {}),
            path_locked=data.get("path_locked", False),
            user_intent=data.get("user_intent"),
            conversation_style=data.get("conversation_style"),
            clarification_count=data.get("clarification_count", 0),
            is_complete=data.get("is_complete", False),
            escalation_reason=data.get("escalation_reason"),
            session_id=data.get("session_id"),
            pending_field=data.get("pending_field"),
        )

        # Restore timestamps
        if "created_at" in data:
            ctx.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            ctx.updated_at = datetime.fromisoformat(data["updated_at"])

        # Restore node states
        for nid, state_data in data.get("node_states", {}).items():
            state = NodeState(
                node_id=nid,
                status=NodeStatus(state_data["status"]),
                visits=state_data["visits"],
                validation_errors=state_data.get("validation_errors", []),
                metadata=state_data.get("metadata", {}),
            )
            if state_data.get("last_visited"):
                state.last_visited = datetime.fromisoformat(state_data["last_visited"])
            ctx.node_states[nid] = state

        # Restore history
        for turn_data in data.get("history", []):
            turn = ConversationTurn(
                timestamp=datetime.fromisoformat(turn_data["timestamp"]),
                role=turn_data["role"],
                content=turn_data["content"],
                node_id=turn_data.get("node_id"),
                metadata=turn_data.get("metadata", {}),
            )
            ctx.history.append(turn)

        return ctx
