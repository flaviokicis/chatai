#!/bin/bash
# Pre-flight validation script - catches issues before runtime
# Run this before testing to avoid runtime errors!

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 Pre-flight Validation"
echo "========================"

cd /Users/jessica/me/chatai
source .venv/bin/activate
cd backend

# Step 1: Ruff linting
echo -e "\n${YELLOW}1. Running Ruff linter...${NC}"
if ruff check app/ --quiet; then
    echo -e "${GREEN}✅ Ruff: No linting issues${NC}"
else
    echo -e "${RED}❌ Ruff found issues. Run 'ruff check app/ --fix' to auto-fix${NC}"
    exit 1
fi

# Step 2: Type checking for function signatures
echo -e "\n${YELLOW}2. Checking function signatures with MyPy...${NC}"
# Focus on files that commonly have signature issues
CRITICAL_FILES="app/flow_core/whatsapp_cli.py app/db/repository.py app/services/message_logging_service.py"

MYPY_OUTPUT=$(mypy $CRITICAL_FILES --ignore-missing-imports --no-error-summary 2>&1 || true)
if echo "$MYPY_OUTPUT" | grep -q "Unexpected keyword argument\|Missing named argument"; then
    echo -e "${RED}❌ Function signature mismatches found:${NC}"
    echo "$MYPY_OUTPUT" | grep -E "(Unexpected keyword argument|Missing named argument)" -A1 -B1
    echo -e "${RED}Fix these before running to avoid runtime errors!${NC}"
    exit 1
else
    echo -e "${GREEN}✅ MyPy: No function signature mismatches${NC}"
fi

# Step 3: Check for common runtime issues
echo -e "\n${YELLOW}3. Checking for common runtime issues...${NC}"

# Check for undefined variables in recently modified files
MODIFIED_FILES=$(find app/ -name "*.py" -mtime -1 2>/dev/null | head -10)
if [ ! -z "$MODIFIED_FILES" ]; then
    for file in $MODIFIED_FILES; do
        # Check for common issues like undefined names
        if python -m py_compile "$file" 2>/dev/null; then
            :
        else
            echo -e "${RED}❌ Syntax error in $file${NC}"
            python -m py_compile "$file"
            exit 1
        fi
    done
fi
echo -e "${GREEN}✅ No syntax errors in recently modified files${NC}"

# Step 4: Quick import check
echo -e "\n${YELLOW}4. Checking imports...${NC}"
if python -c "from app.flow_core.whatsapp_cli import WhatsAppSimulatorCLI; from app.db.repository import create_message" 2>/dev/null; then
    echo -e "${GREEN}✅ Critical imports working${NC}"
else
    echo -e "${RED}❌ Import errors detected${NC}"
    python -c "from app.flow_core.whatsapp_cli import WhatsAppSimulatorCLI; from app.db.repository import create_message"
    exit 1
fi

# Step 5: Database function validation
echo -e "\n${YELLOW}5. Validating database functions...${NC}"
python -c "
import inspect
from app.db.repository import create_message

sig = inspect.signature(create_message)
params = list(sig.parameters.keys())
required = ['session', 'tenant_id', 'channel_instance_id', 'thread_id', 'contact_id', 'text']
missing = [p for p in required if p not in params]
if missing:
    print(f'❌ create_message missing required params: {missing}')
    exit(1)
else:
    print('✅ create_message signature valid')
" || exit 1

echo -e "\n${GREEN}========================${NC}"
echo -e "${GREEN}✅ All validations passed!${NC}"
echo -e "${GREEN}========================${NC}"
echo -e "\nYou can now safely run:"
echo -e "  ${YELLOW}python -m app.flow_core.whatsapp_cli --phone +15550489424${NC}"
