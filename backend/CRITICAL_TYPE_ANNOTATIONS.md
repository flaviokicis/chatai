# Critical Type Annotations Needed in Core Areas

## Overview
After auditing the `/core` folder, here are the critical areas that need better type annotations to prevent runtime errors.

## 🔴 High Priority - Runtime Error Prone

### 1. **AgentState in `state.py`**
```python
# CURRENT - Too loose, accepts Any
def load(self, user_id: str, agent_type: str) -> AgentState | None:
    return data  # type: ignore[no-any-return]

# SHOULD BE - Typed return
from typing import TypedDict

class AgentStateDict(TypedDict):
    answers: dict[str, Any]
    current_node: str | None
    completed: bool

def load(self, user_id: str, agent_type: str) -> AgentStateDict | None:
    # Validate structure before returning
```

**Why it matters**: This returns raw JSON data as `Any`, which can cause AttributeErrors at runtime.

### 2. **Agent Factory in `agent_factory.py`**
```python
# CURRENT - Returns Any
def create_agent_for_flow(self, flow_definition: dict[str, Any], user_id: str) -> Any | None:

# SHOULD BE - Return typed Agent
from app.core.agent_base import Agent

def create_agent_for_flow(self, flow_definition: dict[str, Any], user_id: str) -> Agent | None:
```

**Why it matters**: Returning `Any` means no type checking on agent methods, leading to runtime AttributeErrors.

### 3. **ConversationStore Protocol in `state.py`**
```python
# CURRENT - event is untyped dict
def append_event(self, user_id: str, event: dict) -> None: ...

# SHOULD BE
from typing import TypedDict

class EventDict(TypedDict):
    timestamp: float
    type: str
    data: dict[str, Any]

def append_event(self, user_id: str, event: EventDict) -> None: ...
```

**Why it matters**: Untyped dicts lead to KeyErrors when accessing expected fields.

## 🟡 Medium Priority - Potential Issues

### 4. **Flow Request/Response Types**
```python
# app/core/flow_request.py
@dataclass
class FlowRequest:
    flow_definition: dict[str, Any] | None  # Should be Flow | dict[str, Any]
    flow_metadata: dict[str, Any]  # Should have TypedDict for expected keys
```

### 5. **LLM Client Protocol**
```python
# CURRENT
def extract(self, prompt: str, tools: list[type[object]]) -> dict[str, Any]: ...

# SHOULD BE
from typing import TypeVar, Generic

T = TypeVar('T')

def extract(self, prompt: str, tool: type[T]) -> T: ...
```

## 🟢 Quick Wins - Easy to Fix

### 6. **Message Metadata**
```python
# app/core/message_metadata.py
extra: dict[str, Any] = field(default_factory=dict)

# Should define known keys
class ExtraMetadata(TypedDict, total=False):
    tool_name: str
    confidence: float
    messages: list[dict[str, Any]]
```

### 7. **Router Registry**
```python
# app/core/router.py
registry: dict[str, Callable[[str], Agent]]

# Should be more specific
AgentFactory = Callable[[str], Agent]
registry: dict[str, AgentFactory]
```

## Recommended Type Improvements

### 1. Create Type Aliases
```python
# app/core/types.py
from typing import TypeAlias, TypedDict

UserId: TypeAlias = str
AgentType: TypeAlias = str
SessionId: TypeAlias = str
ThreadId: TypeAlias = str

class FlowDefinitionDict(TypedDict):
    id: str
    entry: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
```

### 2. Use TypedDict for Structured Data
```python
# Instead of dict[str, Any]
class MessagePayload(TypedDict):
    text: str
    delay_ms: int
    type: Literal["text", "button", "list"]

class FlowMetadata(TypedDict):
    flow_id: str
    flow_name: str
    selected_flow_id: str
```

### 3. Add Runtime Validation
```python
from typing import TypeGuard

def is_valid_agent_state(data: Any) -> TypeGuard[AgentStateDict]:
    """Runtime validation for agent state."""
    return (
        isinstance(data, dict) and
        "answers" in data and
        isinstance(data["answers"], dict)
    )

def load(self, user_id: str, agent_type: str) -> AgentStateDict | None:
    data = self._load_raw(user_id, agent_type)
    if data and is_valid_agent_state(data):
        return data
    return None
```

## Implementation Plan

### Phase 1: Critical Runtime Fixes
1. Fix `AgentState` return type in `state.py`
2. Type `create_agent_for_flow` return in `agent_factory.py`
3. Add TypedDict for `flow_metadata` in `flow_request.py`

### Phase 2: Protocol Improvements
1. Define `EventDict` for `append_event`
2. Create typed extraction for LLM client
3. Add validation helpers

### Phase 3: Comprehensive Types
1. Create `app/core/types.py` with common type aliases
2. Replace all `dict[str, Any]` with specific TypedDicts
3. Add runtime validation for external data

## Testing Type Safety

Create a test file to validate critical types:

```python
# test_core_types.py
def test_agent_state_type():
    from app.core.state import RedisStore
    store = RedisStore("redis://localhost")
    
    # This should have proper type
    state = store.load("user123", "flow_agent")
    if state:
        # Should not be Any
        assert hasattr(state, 'answers')  # Type checker should know this

def test_agent_factory_type():
    from app.core.agent_factory import FlowAgentFactory
    factory = FlowAgentFactory(...)
    
    agent = factory.create_agent_for_flow({...}, "user123")
    if agent:
        # Should be typed as Agent
        assert hasattr(agent, 'handle')  # Type checker should validate
```

## MyPy Configuration

Add stricter checking for core modules:

```toml
# pyproject.toml
[[tool.mypy.overrides]]
module = "app.core.*"
disallow_any_expr = true
disallow_any_unimported = true
disallow_any_decorated = false  # Allow property decorators
warn_return_any = true
strict = true
```

## Benefits

Implementing these type annotations will:
1. **Prevent AttributeErrors** - Know what attributes objects have
2. **Prevent KeyErrors** - Know what keys dicts contain
3. **Catch mismatches early** - At type-check time, not runtime
4. **Improve IDE support** - Better autocomplete and refactoring
5. **Document interfaces** - Types serve as documentation

## Priority Order

1. 🔴 Fix `AgentState` type (causes AttributeErrors)
2. 🔴 Fix `create_agent_for_flow` return type
3. 🟡 Add TypedDict for structured dicts
4. 🟢 Create type aliases for clarity
5. 🟢 Add runtime validation helpers
