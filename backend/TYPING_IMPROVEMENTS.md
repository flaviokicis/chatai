# Type Safety Improvements Roadmap

## Current Untyped Areas

### 1. Message Structure ⚠️ **Easy Fix**
**Current:** `list[dict[str, Any]]`  
**Location:** `tools.py`, `flow_types.py`  
**Impact:** Low risk, high benefit

```python
# Current
messages: list[dict[str, Any]]

# Proposed
from app.flow_core.message_types import WhatsAppMessage
messages: list[WhatsAppMessage]
```

### 2. Answers Dictionary 🔴 **Complex**
**Current:** `dict[str, Any]`  
**Location:** `state.py` (FlowContext)  
**Why it's hard:** Flow-dependent, dynamic structure

```python
# Current
answers: dict[str, Any]

# The problem: answers vary by flow
{
    "interesse_inicial": "quadra",  # string
    "dados_ginasio": {"nome": "João", "email": "joao@example.com"},  # dict
    "dimensoes": {"largura": 20, "comprimento": 40},  # numeric dict
}
```

### 3. Updates Dictionary 🔴 **Complex**
**Current:** `dict[str, Any]`  
**Location:** `tools.py` (PerformAction)  
**Why it's hard:** Same as answers - it updates the same structure

### 4. Tenant ID ⚠️ **Import Cycle**
**Current:** `Any | None`  
**Location:** `state.py` (FlowContext)  
**Issue:** Import cycle with UUID

```python
# Current (with comment about the issue!)
tenant_id: Any | None = None  # UUID, but avoiding import cycle

# Fix using TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from uuid import UUID
tenant_id: 'UUID' | None = None
```

### 5. Metadata Fields 🟡 **Medium Complexity**
**Current:** `dict[str, Any]`  
**Locations:** Multiple (ConversationTurn, NodeState, etc.)  
**Why:** Context-dependent, varies by use case

## Why These Were Left Untyped

### 1. **Dynamic Nature of Flows**
- Flows are JSON from database
- Answer types vary per flow  
- Can't know all types at compile time

### 2. **Major Refactoring Required**
Changing `answers` would affect:
- FlowContext
- ToolExecutor  
- LLM prompts
- Database storage
- Frontend API

### 3. **LLM Integration Challenges**
- LLMs generate untyped JSON
- Need flexibility for unexpected structures
- Hard to enforce types on LLM outputs

### 4. **Backwards Compatibility**
- Existing flows expect `dict[str, Any]`
- Would break database records
- API contracts would change

## Recommended Improvements (Priority Order)

### Phase 1: Quick Wins ✅
1. **Fix message typing** (created `message_types.py`)
2. **Fix tenant_id** using TYPE_CHECKING
3. **Add runtime validation** for critical paths

### Phase 2: Medium Risk 🔧
1. **Create answer type registry**
   ```python
   class AnswerRegistry:
       known_types: dict[str, type]
       validators: dict[str, Callable]
   ```

2. **Add Pydantic validation** at boundaries
   ```python
   class ValidatedAnswers(BaseModel):
       class Config:
           extra = "allow"  # For unknown fields
   ```

### Phase 3: Long-term 🎯
1. **Flow schema versioning**
   - v1: Current untyped
   - v2: Typed with validation
   
2. **Generate types from flow definitions**
   ```python
   def generate_answer_types(flow: Flow) -> type:
       """Generate TypedDict from flow definition."""
   ```

## Implementation Strategy

### Step 1: Add Types Without Breaking Changes
```python
# Use Union types during transition
AnswersDict = dict[str, Any]  # Current
TypedAnswers = ...  # New typed version
Answers = AnswersDict | TypedAnswers  # Support both
```

### Step 2: Runtime Validation
```python
def validate_answers(answers: dict, flow: Flow) -> TypedAnswers:
    """Validate and convert to typed structure."""
    # Log warnings but don't fail
    # Gradually increase strictness
```

### Step 3: Migrate Gradually
- Start with new flows
- Add types to existing flows one by one
- Monitor for issues
- Full migration when stable

## Code Debt Tracking

| Area | Risk | Effort | Impact | Priority |
|------|------|--------|--------|----------|
| Message typing | Low | Low | High | P0 ✅ |
| Tenant ID | Low | Low | Medium | P1 |
| Runtime validation | Medium | Medium | High | P1 |
| Answer typing | High | High | High | P2 |
| Full type safety | High | Very High | High | P3 |

## Notes
- The `dict[str, Any]` pattern is intentional in many places
- Full typing would require architectural changes
- Runtime validation is more practical than static typing for flows
- Consider gradual typing with monitoring before full commitment
