#!/bin/bash
# Type checking script to catch function signature mismatches before runtime

set -e

echo "🔍 Running type checks to catch function signature mismatches..."
echo "================================================"

cd /Users/jessica/me/chatai
source .venv/bin/activate
cd backend

# Check only the files that were recently modified
# This is faster than checking everything
echo "Checking recently modified files..."

# Get list of Python files modified in the last commit or working directory
MODIFIED_FILES=$(git diff --name-only HEAD -- '*.py' 2>/dev/null || echo "")
STAGED_FILES=$(git diff --cached --name-only -- '*.py' 2>/dev/null || echo "")

ALL_FILES="$MODIFIED_FILES $STAGED_FILES"

if [ -z "$ALL_FILES" ]; then
    echo "No Python files modified, checking critical modules..."
    # Check critical modules that often have issues
    mypy app/flow_core/whatsapp_cli.py \
         app/db/repository.py \
         app/services/message_logging_service.py \
         app/whatsapp/message_processor.py \
         --ignore-missing-imports \
         --show-error-codes \
         --no-error-summary 2>&1 | grep -E "(error:|note:)" || echo "✅ No type errors found!"
else
    echo "Checking modified files: $ALL_FILES"
    mypy $ALL_FILES \
         --ignore-missing-imports \
         --show-error-codes \
         --no-error-summary 2>&1 | grep -E "(error:|note:)" || echo "✅ No type errors found!"
fi

echo "================================================"
echo "💡 Tip: Add this to your workflow before running the CLI:"
echo "   ./scripts/check_types.sh && python -m app.flow_core.whatsapp_cli"
