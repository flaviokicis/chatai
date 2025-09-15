# Type Checking Guide for Runtime Error Prevention

## Overview
This guide explains how to leverage Python's type system to catch errors at development time instead of runtime.

## Type Stubs Already Installed

✅ **Core Type Stubs** (already installed):
- `types-sqlalchemy` - Database ORM type checking
- `types-redis` - Redis client type checking  
- `types-requests` - HTTP requests type checking
- `types-psycopg2` - PostgreSQL adapter type checking
- `types-setuptools` - Build system type checking
- `types-pytz` - Timezone type checking
- `types-pyyaml` - YAML parsing type checking
- `types-jsonschema` - JSON schema validation type checking

## Packages Without Official Type Stubs

These packages don't have official type stubs but are heavily used:

### 1. **Twilio** (WhatsApp API)
```python
# Add type annotations manually for critical functions
from typing import Any, Dict
from twilio.rest import Client  # type: ignore[import-untyped]

def send_whatsapp_message(client: Client, to: str, body: str) -> Dict[str, Any]:
    ...
```

### 2. **LangChain** (LLM Framework)
```python
# Use protocol types for interfaces
from typing import Protocol

class LLMProtocol(Protocol):
    def invoke(self, prompt: str) -> str: ...
```

### 3. **Pydantic Settings**
```python
# Pydantic has good type support, just need to import correctly
from pydantic import BaseSettings  # Has built-in type hints
```

## Generating Custom Type Stubs

For packages without type stubs, generate your own:

```bash
# Generate stubs for a package
stubgen -p langchain -o stubs/

# Add to PYTHONPATH in mypy.ini
[mypy]
mypy_path = stubs
```

## Enhanced MyPy Configuration

Create `backend/pyproject.toml` additions:

```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
check_untyped_defs = true
strict_optional = true

# Catch function signature mismatches
disallow_any_generics = true
warn_redundant_casts = true
warn_unused_ignores = true
no_implicit_reexport = true

# Critical modules that must be type-safe
[[tool.mypy.overrides]]
module = "app.db.*"
disallow_untyped_defs = true
disallow_incomplete_defs = true
warn_unreachable = true

[[tool.mypy.overrides]]
module = "app.core.*"
disallow_untyped_defs = true

# Allow untyped imports for packages without stubs
[[tool.mypy.overrides]]
module = [
    "twilio.*",
    "langchain.*", 
    "langchain_community.*",
    "mutagen.*",
    "tenacity.*",
    "cryptography.*",
    "starlette.*",
    "pydantic_settings.*"
]
ignore_missing_imports = true
```

## Common Type Patterns to Prevent Runtime Errors

### 1. **Function Signature Validation**
```python
from typing import TypedDict, Required

class CreateMessageParams(TypedDict):
    session: Required[Session]
    tenant_id: Required[UUID]
    channel_instance_id: Required[UUID]
    thread_id: Required[UUID]
    contact_id: UUID | None
    text: str | None
    direction: Required[MessageDirection]
    provider_message_id: str | None

def create_message(**params: Unpack[CreateMessageParams]) -> Message:
    ...
```

### 2. **Dataclass with Validation**
```python
from dataclasses import dataclass
from typing import ClassVar

@dataclass
class ConversationContext:
    tenant_id: UUID
    channel_id: UUID
    thread_id: UUID
    
    # Class variable for validation
    _required_fields: ClassVar[list[str]] = ['tenant_id', 'channel_id', 'thread_id']
    
    def __post_init__(self):
        for field in self._required_fields:
            if getattr(self, field) is None:
                raise ValueError(f"Required field {field} is None")
```

### 3. **Protocol Classes for Duck Typing**
```python
from typing import Protocol

class MessageCreator(Protocol):
    def create_message(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        channel_instance_id: UUID,
        thread_id: UUID,
        contact_id: UUID | None,
        text: str | None,
        direction: MessageDirection,
        **kwargs
    ) -> Message: ...

# Any class implementing this interface will be type-checked
def process_message(creator: MessageCreator, data: dict) -> None:
    ...
```

## Validation Scripts

### Quick Type Check (before running)
```bash
#!/bin/bash
# scripts/quick_type_check.sh
mypy app/flow_core/whatsapp_cli.py \
     app/db/repository.py \
     --ignore-missing-imports \
     --show-error-codes | grep -E "error:"
```

### Full Type Check (in CI/CD)
```bash
#!/bin/bash  
# scripts/full_type_check.sh
mypy app/ \
     --ignore-missing-imports \
     --junit-xml=mypy-report.xml \
     --html-report=mypy-html
```

## Pre-commit Configuration

Already configured in `.pre-commit-config.yaml`:
```yaml
- repo: local
  hooks:
  - id: mypy
    name: MyPy type checker
    entry: mypy app/ --ignore-missing-imports
    language: system
    files: ^backend/app/.*\.py$
```

## Runtime Type Checking (Optional)

For critical functions, add runtime validation:

```python
from typing import get_type_hints
from functools import wraps

def validate_types(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        hints = get_type_hints(func)
        # Validate kwargs match expected types
        for param, expected_type in hints.items():
            if param in kwargs:
                value = kwargs[param]
                if not isinstance(value, expected_type):
                    raise TypeError(f"{param} must be {expected_type}, got {type(value)}")
        return func(*args, **kwargs)
    return wrapper

@validate_types
def create_message(session: Session, *, tenant_id: UUID, ...) -> Message:
    ...
```

## Best Practices

1. **Always run type checking before commits** - Use pre-commit hooks
2. **Type check after refactoring** - Run `./scripts/check_types.sh`
3. **Use TypedDict for complex parameters** - Prevents wrong argument names
4. **Prefer keyword-only arguments** - Forces named parameters with `*`
5. **Add type stubs for new packages** - Use `stubgen` or write manually
6. **Document expected types in docstrings** - Even without full type hints
7. **Use Protocol classes for interfaces** - Better than abstract base classes

## Common Errors Prevented

✅ **Wrong parameter names**: `content=` vs `text=`
✅ **Missing required parameters**: `tenant_id`, `channel_instance_id`  
✅ **Wrong parameter types**: Passing `str` instead of `UUID`
✅ **None values where not allowed**: Strict optional checking
✅ **Wrong return types**: Function returning wrong type
✅ **Attribute errors**: Accessing non-existent attributes

## Workflow Integration

### Development Workflow
```bash
# 1. Write/modify code
vim app/some_module.py

# 2. Quick type check
./scripts/check_types.sh

# 3. Fix any issues
# 4. Run pre-commit
pre-commit run --all-files

# 5. Test
python -m app.flow_core.whatsapp_cli
```

### CI/CD Integration
```yaml
# .github/workflows/type_check.yml
- name: Type Check
  run: |
    mypy app/ --junit-xml=mypy-report.xml
    
- name: Upload MyPy Report
  uses: actions/upload-artifact@v3
  with:
    name: mypy-report
    path: mypy-report.xml
```

## Troubleshooting

### "Cannot find implementation or library stub"
- Install type stubs: `uv add --dev types-<package>`
- Or add to mypy config: `ignore_missing_imports = true`
- Or generate stubs: `stubgen -p <package>`

### "Unexpected keyword argument"
- This is exactly what we want to catch! Fix the function call.

### "Incompatible type"  
- Check if you need to cast: `cast(UUID, some_value)`
- Or use type guards: `if isinstance(value, UUID):`

## Further Resources

- [MyPy Documentation](https://mypy.readthedocs.io/)
- [Python Type Hints Cheat Sheet](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html)
- [Typeshed (Collection of Type Stubs)](https://github.com/python/typeshed)
- [PEP 484 - Type Hints](https://www.python.org/dev/peps/pep-0484/)
