from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class GuardRef(BaseModel):
    """Reference to a guard function with arguments."""

    fn: str
    args: dict[str, object] = Field(default_factory=dict)
    # New: LLM hints for intelligent evaluation
    description: str | None = None
    weight: float = 1.0  # Importance weight for LLM consideration


class Edge(BaseModel):
    """Edge connecting two nodes in the flow."""

    source: str
    target: str
    guard: GuardRef | None = None
    priority: int = 0
    # New: Edge metadata for LLM understanding
    label: str | None = None
    condition_description: str | None = None  # Human-readable condition


class BaseNode(BaseModel):
    """Base class for all node types."""

    id: str
    kind: Literal["Question", "Decision", "Terminal", "Action", "Subflow"]
    label: str | None = None
    meta: dict[str, object] = Field(default_factory=dict)
    # New: Node behavior hints
    skippable: bool = False
    revisitable: bool = True
    max_attempts: int = 3


class QuestionNode(BaseNode):
    """Node that asks a question and collects an answer."""

    kind: Literal["Question"] = "Question"
    key: str
    prompt: str
    validator: str | None = None
    # New: Enhanced question properties
    clarification: str | None = None  # Extended explanation if needed
    examples: list[str] = Field(default_factory=list)
    allowed_values: list[str] | None = None
    data_type: Literal["text", "number", "boolean", "date", "email", "phone", "url"] = "text"
    required: bool = False
    dependencies: list[str] = Field(default_factory=list)  # Keys this depends on
    priority: int = 100


class DecisionNode(BaseNode):
    """Node that makes routing decisions based on state."""

    kind: Literal["Decision"] = "Decision"
    # New: Decision metadata
    decision_type: Literal["automatic", "llm_assisted", "user_choice"] = "automatic"
    decision_prompt: str | None = None  # For user_choice type


class TerminalNode(BaseNode):
    """Node that ends the flow."""

    kind: Literal["Terminal"] = "Terminal"
    reason: str | None = None
    # New: Terminal behavior
    success: bool = True
    next_flow: str | None = None  # Chain to another flow
    handoff_required: bool = False


class ActionNode(BaseNode):
    """Node that performs an action (API call, calculation, etc.)."""

    kind: Literal["Action"] = "Action"
    action_type: str  # Type of action to perform
    action_config: dict[str, Any] = Field(default_factory=dict)
    # Store results in these keys
    output_keys: list[str] = Field(default_factory=list)


class SubflowNode(BaseNode):
    """Node that invokes another flow as a subflow."""

    kind: Literal["Subflow"] = "Subflow"
    flow_ref: str  # Reference to another flow
    # Parameter mapping from parent to child
    input_mapping: dict[str, str] = Field(default_factory=dict)
    # Result mapping from child to parent
    output_mapping: dict[str, str] = Field(default_factory=dict)


Node = Annotated[
    QuestionNode | DecisionNode | TerminalNode | ActionNode | SubflowNode,
    Field(discriminator="kind"),
]


class ValidationRule(BaseModel):
    """Validation rule for answers."""

    type: Literal["regex", "range", "length", "custom"]
    pattern: str | None = None  # For regex
    min_value: float | None = None  # For range
    max_value: float | None = None  # For range
    min_length: int | None = None  # For length
    max_length: int | None = None  # For length
    function: str | None = None  # For custom
    error_message: str | None = None


class PolicyPathSelection(BaseModel):
    """Policy for path selection in multi-path flows."""

    lock_threshold: int = 2
    allow_switch_before_lock: bool = True
    confidence_threshold: float = 0.7  # New: minimum confidence for path selection
    use_llm: bool = True  # New: whether to use LLM for path selection


class PolicyConversation(BaseModel):
    """Policy for conversation behavior."""

    allow_clarifications: bool = True
    max_clarifications: int = 3
    allow_skip: bool = False
    allow_revisit: bool = True
    conversation_style: Literal["formal", "casual", "technical", "adaptive"] = "adaptive"
    use_examples: bool = True
    maintain_context: bool = True


class PolicyValidation(BaseModel):
    """Policy for answer validation."""

    strict_validation: bool = False
    max_validation_attempts: int = 3
    validation_strategy: Literal["immediate", "deferred", "batch"] = "immediate"


class Policies(BaseModel):
    """Flow policies controlling behavior."""

    path_selection: PolicyPathSelection | None = None
    conversation: PolicyConversation = Field(default_factory=PolicyConversation)
    validation: PolicyValidation = Field(default_factory=PolicyValidation)


class FlowUILabels(BaseModel):
    """UI labels and text customization for flow display."""
    
    global_section_label: str = "Global Questions"
    branch_section_prefix: str = "Path"
    terminal_completion_label: str = "Flow Completed"
    
    # Language/locale specific
    locale: str = "en"


class FlowMetadata(BaseModel):
    """Metadata about the flow."""

    name: str
    description: str | None = None
    version: str = "1.0.0"
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    
    # UI customization
    ui_labels: FlowUILabels = Field(default_factory=FlowUILabels)


class Flow(BaseModel):
    """Complete flow definition."""

    schema_version: Literal["v1", "v2"] = "v1"  # Support both v1 and v2
    id: str
    metadata: FlowMetadata | None = None
    entry: str
    nodes: list[Node]
    edges: list[Edge]
    policies: Policies = Field(default_factory=Policies)
    # New: Validation rules
    validations: dict[str, ValidationRule] = Field(default_factory=dict)
    # New: Global context/variables
    context: dict[str, Any] = Field(default_factory=dict)
    # New: Subflows
    subflows: dict[str, Flow] = Field(default_factory=dict)

    def node_by_id(self, node_id: str) -> Node | None:
        """Get node by ID."""
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def questions_by_priority(self) -> list[QuestionNode]:
        """Get question nodes sorted by priority."""
        questions = [n for n in self.nodes if isinstance(n, QuestionNode)]
        return sorted(questions, key=lambda q: q.priority)

    def get_dependencies(self, node_id: str) -> list[str]:
        """Get dependencies for a node."""
        node = self.node_by_id(node_id)
        if isinstance(node, QuestionNode):
            return node.dependencies
        return []
