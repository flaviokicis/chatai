# Preventing Runtime Errors: Type System Solutions

## The Two Errors You Just Hit

### 1. Type Mismatch Error
```python
AttributeError: 'Redis' object has no attribute 'load'
```

**Root Cause**: Passing `Redis` client instead of `RedisStore` to `RedisSessionManager`

**How Type Checking Would Prevent This:**

```python
# With proper type annotations:
class RedisSessionManager(SessionManager):
    def __init__(self, store: ConversationStore):  # ← Type annotation
        self._store = store

# MyPy would catch this:
redis_client = Redis.from_url(...)
session_manager = RedisSessionManager(redis_client)  
# ❌ Error: Argument has incompatible type "Redis"; expected "ConversationStore"

# Correct way:
redis_store = RedisStore(redis_url)  # Implements ConversationStore
session_manager = RedisSessionManager(redis_store)  # ✅ Type-safe
```

### 2. Uninitialized Variable Error
```python
UnboundLocalError: cannot access local variable 'existing_context' where it is not associated with a value
```

**Root Cause**: Variable referenced in exception handler before assignment

**How to Prevent:**

```python
# ❌ BAD: Variable may not be defined
def process():
    try:
        existing_context = load_context()  # May fail
        # ... use existing_context
    except Exception as e:
        return existing_context  # UnboundLocalError if load_context() failed

# ✅ GOOD: Initialize before try block
def process():
    existing_context = None  # Initialize early
    try:
        existing_context = load_context()
        # ... use existing_context
    except Exception as e:
        return existing_context  # Always defined
```

## Systematic Prevention Strategies

### 1. Use Protocol Classes for Interfaces

```python
from typing import Protocol

class ConversationStore(Protocol):
    """Define the expected interface"""
    def load(self, user_id: str, session_id: str) -> dict | None: ...
    def save(self, user_id: str, session_id: str, data: dict) -> None: ...

class RedisStore:
    """Implements ConversationStore protocol"""
    def load(self, user_id: str, session_id: str) -> dict | None:
        # Implementation
        pass
    
    def save(self, user_id: str, session_id: str, data: dict) -> None:
        # Implementation
        pass

# Type checker ensures RedisStore implements ConversationStore
```

### 2. Use Abstract Base Classes

```python
from abc import ABC, abstractmethod

class ConversationStore(ABC):
    @abstractmethod
    def load(self, user_id: str, session_id: str) -> dict | None:
        """Load conversation state"""
        pass
    
    @abstractmethod
    def save(self, user_id: str, session_id: str, data: dict) -> None:
        """Save conversation state"""
        pass

# Runtime error if RedisStore doesn't implement all methods
class RedisStore(ConversationStore):
    # Must implement load() and save() or get TypeError at instantiation
    pass
```

### 3. Use NewType for Semantic Types

```python
from typing import NewType

# Create semantic types to prevent mix-ups
UserId = NewType('UserId', str)
SessionId = NewType('SessionId', str)
ThreadId = NewType('ThreadId', UUID)

def process_message(
    user_id: UserId,
    session_id: SessionId,
    thread_id: ThreadId
) -> None:
    # Type checker ensures correct parameter types
    pass

# Usage:
user = UserId("user123")
session = SessionId("session456")
thread = ThreadId(uuid4())
process_message(user, session, thread)  # ✅ Type-safe

# This would be caught:
process_message(session, user, thread)  # ❌ Type error
```

### 4. Enable Strict MyPy Settings

Add to `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.12"

# Catch uninitialized variables
warn_unreachable = true
warn_return_any = true
check_untyped_defs = true

# Catch type mismatches
disallow_any_generics = true
strict_optional = true
warn_redundant_casts = true

# Force type annotations
disallow_untyped_defs = true
disallow_incomplete_defs = true

# Specific module overrides
[[tool.mypy.overrides]]
module = "app.services.*"
strict = true  # Extra strict for service layer
```

### 5. Use Pydantic for Runtime Validation

```python
from pydantic import BaseModel, validator

class SessionConfig(BaseModel):
    store: ConversationStore  # Will validate at runtime
    
    @validator('store')
    def validate_store(cls, v):
        if not hasattr(v, 'load') or not hasattr(v, 'save'):
            raise ValueError("Store must implement load() and save() methods")
        return v

# This will fail at runtime with clear error:
config = SessionConfig(store=Redis())  # ❌ ValidationError
```

### 6. Use Type Guards

```python
from typing import TypeGuard

def is_conversation_store(obj: object) -> TypeGuard[ConversationStore]:
    """Runtime check that object implements ConversationStore"""
    return (
        hasattr(obj, 'load') and 
        hasattr(obj, 'save') and
        callable(obj.load) and
        callable(obj.save)
    )

def create_session_manager(store: object) -> RedisSessionManager:
    if not is_conversation_store(store):
        raise TypeError(f"{store} does not implement ConversationStore")
    return RedisSessionManager(store)
```

## Automated Prevention Workflow

### 1. Pre-commit Hook (Already Added)
```yaml
- repo: local
  hooks:
  - id: mypy
    name: MyPy type checker
    entry: mypy app/ --show-error-codes
```

### 2. IDE Integration
VS Code `settings.json`:
```json
{
    "python.linting.mypyEnabled": true,
    "python.linting.mypyArgs": [
        "--show-error-codes",
        "--warn-unreachable",
        "--strict-optional"
    ]
}
```

### 3. CI/CD Pipeline
```yaml
- name: Type Check
  run: |
    mypy app/ --junit-xml=mypy-report.xml
    if grep -q "incompatible type\|UnboundLocalError" mypy-report.xml; then
      echo "Type errors found!"
      exit 1
    fi
```

### 4. Runtime Assertions (Development Only)
```python
import sys

if sys.flags.dev_mode:  # Only in development
    from typing import get_type_hints
    
    def validate_types(func):
        """Runtime type validation decorator"""
        def wrapper(*args, **kwargs):
            hints = get_type_hints(func)
            # Validate types at runtime
            return func(*args, **kwargs)
        return wrapper
else:
    # No-op in production
    def validate_types(func):
        return func
```

## Quick Checks Before Running

```bash
#!/bin/bash
# quick_check.sh

echo "🔍 Checking for type mismatches..."
mypy app/ --no-error-summary 2>&1 | grep -E "(incompatible type|UnboundLocalError|has no attribute)" && {
    echo "❌ Type errors found! Fix before running."
    exit 1
} || echo "✅ No type mismatches detected"

echo "🔍 Checking for uninitialized variables..."
python -m pyflakes app/ 2>&1 | grep -E "(undefined name|local variable)" && {
    echo "❌ Potential uninitialized variables! Fix before running."
    exit 1
} || echo "✅ No uninitialized variables detected"
```

## Key Takeaways

1. **Type annotations are not just documentation** - They prevent runtime errors
2. **Initialize variables before try blocks** - Avoid UnboundLocalError
3. **Use Protocol/ABC for interfaces** - Ensure implementations match expectations
4. **Enable strict MyPy settings** - Catch more issues at development time
5. **Add runtime validation for critical paths** - Belt and suspenders approach
6. **Automate checks in your workflow** - Pre-commit, IDE, CI/CD

## The Pattern That Would Have Saved You

```python
# 1. Define clear interfaces
from typing import Protocol

class StoreProtocol(Protocol):
    def load(self, ...) -> ...: ...
    def save(self, ...) -> ...: ...

# 2. Type your dependencies
class SessionManager:
    def __init__(self, store: StoreProtocol) -> None:
        self._store = store

# 3. Initialize variables early
def process() -> Optional[Context]:
    context = None  # Always initialize
    try:
        context = load_context()
    except Exception:
        return context  # Safe to reference

# 4. Run type checker before testing
# mypy app/ && python -m app.flow_core.whatsapp_cli
```

With these patterns, both errors would have been caught before runtime!
