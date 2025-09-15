# Makefile Validation Commands

## Overview

The Makefile now includes validation commands that catch runtime errors before they happen. These replace the bash script with integrated Make targets.

## Available Commands

### `make validate`
**Full validation** - comprehensive pre-flight checks (takes ~10-15 seconds):

```bash
make validate
```

**What it checks:**
1. **Critical Ruff errors** - Syntax errors, unused imports, undefined names
2. **Function signature mismatches** - Wrong parameter names, missing required params
3. **Syntax errors** in recently modified files
4. **Import validation** - Critical modules can be imported
5. **Database function signatures** - `create_message()` has correct parameters

**When to use:** Before major testing sessions, after refactoring, before commits

### `make validate-quick`
**Quick validation** - essential checks only (takes ~3-5 seconds):

```bash
make validate-quick
```

**What it checks:**
1. **Function signature mismatches** - The exact errors you hit
2. **Import validation** - Critical modules work

**When to use:** Before every CLI run, during development iterations

### `make whatsapp-cli`
**Run WhatsApp CLI** with the validated codebase:

```bash
make whatsapp-cli
```

Equivalent to: `python -m app.flow_core.whatsapp_cli --phone +15550489424`

## Recommended Workflow

### Before Testing
```bash
# Quick check (3 seconds)
make validate-quick && make whatsapp-cli

# Or full validation (10 seconds)  
make validate && make whatsapp-cli
```

### After Refactoring
```bash
# Always run full validation after major changes
make validate
```

### Pre-commit (Automatic)
The pre-commit hooks now include MyPy type checking, so these errors are caught automatically on `git commit`.

## Example Output

### ✅ Success
```bash
🚀 Pre-flight Validation
========================

1. Running Ruff linter (critical errors only)...
✅ Ruff: No critical errors (style warnings ignored)

2. Checking function signatures with MyPy...
✅ MyPy: No function signature mismatches

3. Checking for syntax errors in recently modified files...
✅ No syntax errors in recently modified files

4. Checking critical imports...
✅ Critical imports working

5. Validating database functions...
✅ Database function signatures valid

========================
✅ All validations passed!
========================

You can now safely run:
  make whatsapp-cli
```

### ❌ Function Signature Error (Caught!)
```bash
2. Checking function signatures with MyPy...
❌ Function signature mismatches found:
app/flow_core/whatsapp_cli.py:559: error: Unexpected keyword argument "content" for "create_message"
app/flow_core/whatsapp_cli.py:559: error: Unexpected keyword argument "external_id" for "create_message"
app/flow_core/whatsapp_cli.py:559: error: Missing named argument "tenant_id" for "create_message"
Fix these before running to avoid runtime errors!
```

This is **exactly** the error you hit at runtime - now caught at development time!

## Integration with CI/CD

The `ci` target now includes validation:

```bash
make ci  # Runs: lint fmt typecheck validate test
```

## Error Types Prevented

### 1. Function Signature Mismatches
- ❌ `content=` instead of `text=`
- ❌ `external_id=` instead of `provider_message_id=`
- ❌ Missing required parameters (`tenant_id`, `channel_instance_id`)

### 2. Type Mismatches  
- ❌ Passing `Redis` instead of `RedisStore`
- ❌ Wrong parameter types

### 3. Import Errors
- ❌ Missing dependencies
- ❌ Circular imports
- ❌ Module not found

### 4. Syntax Errors
- ❌ Python syntax mistakes
- ❌ Indentation errors
- ❌ Undefined variables

## Performance

- **`validate-quick`**: ~3-5 seconds (function signatures + imports)
- **`validate`**: ~10-15 seconds (comprehensive checks)
- **`validate` + `whatsapp-cli`**: ~15-20 seconds total

Compare to: Finding runtime error → debugging → fixing → restarting = **5+ minutes**

## Customization

To add more validation steps, edit the Makefile:

```makefile
validate:
    # Add new validation step
    @echo "\033[1;33m6. Custom validation...\033[0m"
    @if custom-check; then \
        echo "\033[0;32m✅ Custom check passed\033[0m"; \
    else \
        echo "\033[0;31m❌ Custom check failed\033[0m"; \
        exit 1; \
    fi
```

## Key Benefits

1. **Catch errors at development time** - No more runtime surprises
2. **Fast feedback loop** - 3-5 seconds vs 5+ minutes of debugging
3. **Integrated workflow** - Part of your normal Make commands
4. **Comprehensive coverage** - Function signatures, imports, syntax
5. **CI/CD ready** - Automated validation in pipelines

## Migration from Script

**Old way:**
```bash
./scripts/validate_before_run.sh
python -m app.flow_core.whatsapp_cli --phone +15550489424
```

**New way:**
```bash
make validate-quick && make whatsapp-cli
# Or simply:
make validate && make whatsapp-cli
```

The Makefile approach is:
- ✅ Faster to type
- ✅ Integrated with other build tasks
- ✅ Easier to customize
- ✅ Better error formatting
- ✅ Cross-platform compatible
