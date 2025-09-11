#!/bin/bash
# Type checking script to catch interface mismatches

set -e

echo "🔍 Running type checks..."

# Activate virtual environment
source .venv/bin/activate

# Core modules that must be type-safe
CORE_MODULES=(
    "app/flow_core/engine.py"
    "app/flow_core/runner.py" 
    "app/flow_core/llm_responder.py"
    "app/flow_core/services/responder.py"
    "app/flow_core/services/tool_executor.py"
    "app/core/flow_processor.py"
)

echo "Checking core modules for interface mismatches..."

# Run mypy on core modules - focus on critical errors
mypy "${CORE_MODULES[@]}" \
    --show-error-codes \
    --no-error-summary \
    --follow-imports=silent \
    2>&1 | grep -E "(call-arg|attr-defined|arg-type|assignment)" || echo "✅ No critical interface errors"

echo ""
echo "🎯 Type checking complete!"
echo ""
echo "To run full type check: mypy app/"
echo "To add to CI: Add this script to your pre-commit hooks"
