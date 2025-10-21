# Flow Core Architecture

## Overview

The Flow Core is an LLM-oriented state machine that enables flexible, intelligent conversations while maintaining structure and achieving business goals. It represents the **template** or **script** that agents follow, providing guardrails while allowing natural conversation flow.

## Philosophy

We're not building dumb automation - we're orchestrating smart LLMs. The flow provides:
- **Structure**: A script/template defining the conversation goals
- **Flexibility**: LLMs can clarify, skip, revisit as needed for natural conversation
- **Intelligence**: Context-aware decisions, not rigid state transitions
- **Guardrails**: Ensuring business objectives are met while being conversational

## Core Concepts

### 1. Flow (The Template)
The **Flow** is the template/script that defines:
- What information needs to be collected
- The logical sequence and dependencies
- Validation rules and constraints
- Conversation policies and style
- Paths and branches based on context

```python
Flow(
    id="sales_qualification",
    metadata=FlowMetadata(name="Sales Qualifier", version="1.0.0"),
    nodes=[...],  # Questions, decisions, actions
    edges=[...],  # Transitions with guards
    policies=Policies(
        conversation=PolicyConversation(
            allow_clarifications=True,
            conversation_style="adaptive"
        )
    )
)
```

### 2. Nodes
Different node types for different purposes:

- **QuestionNode**: Collects information from the user
- **DecisionNode**: Routes based on state/context
- **ActionNode**: Performs actions (API calls, calculations)
- **SubflowNode**: Invokes nested flows
- **TerminalNode**: Ends the flow

### 3. LLM-Oriented Engine
The engine orchestrates flow execution with LLM intelligence:

```python
engine = LLMFlowEngine(
    compiled_flow,
    llm_client,
    strict_mode=False  # Flexible, LLM-assisted mode
)
```

Key features:
- **Contextual prompts**: Adapts questions based on conversation
- **Intelligent routing**: LLM helps select best path
- **Natural clarifications**: Handles "what do you mean?" naturally
- **Smart recovery**: Handles unexpected inputs gracefully

### 4. Tool-Based Interactions
All LLM interactions use tool calling, not separate prompts:

```python
# Tools the LLM can use
PerformAction         # Unified tool for all conversation actions (stay, update, navigate, handoff, complete, restart)
RequestHumanHandoff   # Escalate to human agent (also available via PerformAction)
ModifyFlowLive        # Modify flow behavior (admin only)
```

### 5. Rich Context Management
The `FlowContext` maintains full conversation state:

```python
context = FlowContext(
    flow_id="sales",
    answers={"intention": "buy_leds"},
    history=[...],  # Full conversation history
    node_states={...},  # Track visits, attempts
    path_confidence={"tennis": 0.8},  # Path selection confidence
    conversation_style="casual",  # Detected style
)
```

## Architecture Layers

### 1. IR (Intermediate Representation)
- Defines the flow structure (nodes, edges, policies)
- Version-controlled schema
- Supports validation rules and metadata

### 2. Compiler
- Validates flow structure
- Resolves references
- Optimizes for execution
- Detects cycles and unreachable nodes

### 3. Engine
- Executes the compiled flow
- Manages state transitions
- Integrates LLM for intelligent decisions
- Handles context and history

### 4. Responder
- Uses LLM tool calling for interactions
- Extracts information from user messages
- Generates contextual responses
- Handles clarifications and edge cases

## Usage Patterns

### Simple Information Collection
```python
flow = Flow(
    nodes=[
        QuestionNode(key="name", prompt="What's your name?"),
        QuestionNode(key="email", prompt="What's your email?"),
    ]
)
```

### Branching Based on Answers
```python
edges=[
    Edge(
        source="router",
        target="new_customer_flow",
        guard=GuardRef(
            fn="answers_equals",
            args={"key": "customer_type", "value": "new"}
        )
    )
]
```

### Multi-Path Flows
```python
# Paths for different customer segments
paths = {
    "enterprise": {...},
    "small_business": {...},
    "individual": {...}
}
# LLM selects path based on conversation
```

### Validation and Constraints
```python
validations={
    "email": ValidationRule(type="regex", pattern=r".*@.*\..*"),
    "age": ValidationRule(type="range", min_value=18, max_value=120)
}
```

## Migration from V1

The system is backward compatible. Existing flows work as-is:

```python
# Create flow engine
from app.flow_core.engine import LLMFlowEngine

engine = LLMFlowEngine(llm_client, compiled_flow)
```

## Best Practices

### 1. Design for Conversation
- Write prompts as natural questions
- Provide clarification text for complex questions
- Include examples when helpful
- Allow skipping non-critical questions

### 2. Use Guards Wisely
- Guards are suggestions, not hard blocks
- LLM can override when context suggests it
- Use `condition_description` for human-readable conditions

### 3. Leverage Context
- Use conversation history for better responses
- Detect user frustration and adapt
- Maintain conversation style consistency

### 4. Handle Edge Cases
- Set max attempts for validation
- Provide escalation paths
- Allow revisiting answers
- Support clarification requests

### 5. Test Thoroughly
- Test happy paths
- Test clarification flows
- Test validation failures
- Test path selection
- Test escalation scenarios

## Configuration

### Flow Policies
```python
policies:
  conversation:
    allow_clarifications: true
    max_clarifications: 3
    conversation_style: adaptive
    allow_skip: true
    allow_revisit: true
  
  validation:
    strict_validation: false
    max_validation_attempts: 3
  
  path_selection:
    use_llm: true
    confidence_threshold: 0.7
```

### Node Configuration
```python
QuestionNode(
    key="email",
    prompt="What's your email?",
    skippable=True,
    revisitable=True,
    max_attempts=3,
    clarification="We need this to send confirmation",
    examples=["john@example.com"],
    data_type="email"
)
```

## Future Enhancements

1. **Visual Editor Integration**
   - Export flow to visual format
   - Import from visual editor
   - Real-time preview

2. **Advanced Guards**
   - Complex boolean expressions
   - Cross-field validations
   - External API validations

3. **Analytics**
   - Track node visits and durations
   - Identify drop-off points
   - A/B testing support

4. **Subflow Library**
   - Reusable subflows
   - Industry-specific templates
   - Best practice patterns

5. **Multi-Modal Support**
   - Voice interactions
   - File uploads
   - Rich media responses
