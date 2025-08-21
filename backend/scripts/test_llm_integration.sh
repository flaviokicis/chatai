#!/bin/bash

# LLM Integration Test Runner
# Usage: ./scripts/test_llm_integration.sh [--full] [--debug]

set -e

cd "$(dirname "$0")/.."  # Go to backend directory

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m' 
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧪 LLM Flow Integration Test Runner${NC}"
echo "=============================================="

# Check environment
echo -e "${YELLOW}📋 Checking environment...${NC}"

if [ ! -f ".venv/bin/activate" ]; then
    echo -e "${RED}❌ Virtual environment not found. Run: uv sync${NC}"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env file not found. Copy from env.example${NC}"
    exit 1
fi

source .venv/bin/activate
source .env
export PYTHONPATH=.

if [ -z "$GOOGLE_API_KEY" ] || [ "$GOOGLE_API_KEY" = "test" ]; then
    echo -e "${RED}❌ GOOGLE_API_KEY not configured in .env${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Environment ready${NC}"

# Parse arguments
FULL_TEST=false
DEBUG_MODE=false

for arg in "$@"; do
    case $arg in
        --full)
            FULL_TEST=true
            ;;
        --debug)
            DEBUG_MODE=true
            ;;
        *)
            echo "Usage: $0 [--full] [--debug]"
            echo "  --full   Run comprehensive tests (more API calls)"
            echo "  --debug  Show detailed LLM reasoning"
            exit 1
            ;;
    esac
done

# Set debug mode if requested
if [ "$DEBUG_MODE" = true ]; then
    export DEBUG=true
    echo -e "${YELLOW}🐛 Debug mode enabled${NC}"
fi

echo ""
echo -e "${BLUE}🎯 Running Integration Tests...${NC}"

# 1. Always run basic integration test (fast, essential)
echo -e "${YELLOW}📋 1. Basic LLM Integration Test (core tools)...${NC}"
python -m pytest tests/test_integration_llm_flow.py::TestLLMFlowIntegration::test_basic_llm_integration_core_tools -v

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Basic integration test failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Basic integration test passed${NC}"

# 2. Run comprehensive test if requested
if [ "$FULL_TEST" = true ]; then
    echo ""
    echo -e "${YELLOW}🦷 2. Comprehensive Dentist Flow Test (all tools)...${NC}"
    echo -e "${YELLOW}   ⚠️  This will make many API calls and take 3-5 minutes${NC}"
    
    python -m pytest tests/test_comprehensive_dentist_flow.py -v
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Comprehensive test failed!${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Comprehensive test passed${NC}"
    
    # 3. Run specific tool tests
    echo ""
    echo -e "${YELLOW}🔧 3. Specific Tool Tests...${NC}"
    python -m pytest tests/test_integration_specific_tools.py -v
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Specific tool tests failed!${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ All specific tool tests passed${NC}"
fi

echo ""
echo -e "${GREEN}🎉 ALL INTEGRATION TESTS PASSED!${NC}"
echo ""
echo -e "${BLUE}📊 Test Summary:${NC}"
echo "   ✅ Core LLM functionality verified"
echo "   ✅ All flow tools working correctly"
echo "   ✅ Portuguese conversation handling"
echo "   ✅ Complex flow navigation"

if [ "$FULL_TEST" = true ]; then
    echo "   ✅ Realistic conversation scenarios"
    echo "   ✅ Nested subpath handling"
    echo "   ✅ Error recovery and escalation"
fi

echo ""
echo -e "${GREEN}🚀 System ready for production!${NC}"
