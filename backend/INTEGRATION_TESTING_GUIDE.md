# 🧪 LLM Flow Integration Testing Guide

## Quick Start

### 1. **Run All Integration Tests**
```bash
cd backend
source .venv/bin/activate
source .env  # Loads GOOGLE_API_KEY
python -m pytest tests/test_*integration*.py -v
```

### 2. **Run Individual Test Suites**
```bash
# Basic integration (fast, few API calls)
pytest tests/test_integration_llm_flow.py::TestLLMFlowIntegration::test_basic_llm_integration_core_tools -v -s

# Comprehensive dentist flow (realistic, many API calls)  
pytest tests/test_comprehensive_dentist_flow.py -v -s

# Specific tools (focused testing)
pytest tests/test_integration_specific_tools.py -v -s
```

### 3. **Debug Mode (see all LLM calls)**
```bash
# Run with debug output to see LLM reasoning
DEVELOPMENT_MODE=true pytest tests/test_comprehensive_dentist_flow.py -v -s
```

## 🔑 Environment Setup

### Required Environment Variables
```bash
# In backend/.env
GOOGLE_API_KEY=your_actual_api_key_here
LLM_MODEL=gemini-2.5-flash-lite  # Cost-effective for testing
```

### Test Environment Check
```bash
# Verify environment is ready
cd backend
source .venv/bin/activate
python -c "
import os
from langchain.chat_models import init_chat_model
from app.core.langchain_adapter import LangChainToolsLLM

api_key = os.environ.get('GOOGLE_API_KEY')
if not api_key or api_key == 'test':
    print('❌ GOOGLE_API_KEY not configured')
    exit(1)

try:
    chat = init_chat_model('gemini-2.5-flash-lite', model_provider='google_genai')
    llm = LangChainToolsLLM(chat)
    result = llm.extract('Test message', [])
    print('✅ LLM integration working!')
except Exception as e:
    print(f'❌ LLM setup failed: {e}')
    exit(1)
"
```

## 🚀 CI/CD Integration

### GitHub Actions Workflow
```yaml
# .github/workflows/integration-tests.yml
name: LLM Integration Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
        
    - name: Install dependencies
      run: |
        cd backend
        pip install uv
        uv sync
        
    - name: Run basic integration tests
      env:
        GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
      run: |
        cd backend
        source .venv/bin/activate
        pytest tests/test_integration_llm_flow.py::TestLLMFlowIntegration::test_basic_llm_integration_core_tools -v
        
    - name: Run comprehensive tests (on main branch only)
      if: github.ref == 'refs/heads/main'
      env:
        GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
      run: |
        cd backend
        source .venv/bin/activate
        pytest tests/test_comprehensive_dentist_flow.py -v
```

### Local Pre-commit Hook
```bash
# .git/hooks/pre-commit
#!/bin/bash
cd backend
source .venv/bin/activate
source .env

# Run quick integration test before commit
echo "🧪 Running basic LLM integration test..."
python -m pytest tests/test_integration_llm_flow.py::TestLLMFlowIntegration::test_basic_llm_integration_core_tools -q

if [ $? -ne 0 ]; then
    echo "❌ Integration test failed! Fix before committing."
    exit 1
fi

echo "✅ Integration test passed!"
```

## 💰 Cost Management

### API Usage Optimization
```bash
# Use cheaper model for most tests
export LLM_MODEL="gemini-2.5-flash-lite"

# Run subset of tests daily
pytest tests/test_integration_llm_flow.py::TestLLMFlowIntegration::test_basic_llm_integration_core_tools

# Run comprehensive tests weekly/before releases
pytest tests/test_comprehensive_dentist_flow.py
```

### Rate Limit Management
```python
# Already implemented in tests:
def rate_limit_delay():
    """Add delay to avoid hitting API rate limits."""
    time.sleep(1.0)  # Adjust based on your API tier
```

### Test Markers for Selective Running
```bash
# Mark expensive tests
@pytest.mark.slow
@pytest.mark.llm_intensive

# Run only fast tests
pytest -m "not slow"

# Run LLM tests only when needed
pytest -m "llm_intensive" --llm-budget=high
```

## 📁 Test File Organization

### Current Structure
```
backend/tests/
├── test_integration_llm_flow.py          # Basic + comprehensive flow tests
├── test_integration_specific_tools.py    # Individual tool tests  
├── test_comprehensive_dentist_flow.py    # Realistic conversation test
├── fixtures/
│   └── dentist_flow.json                 # Complex flow definition
└── conftest.py                           # Shared fixtures
```

### Adding New Integration Tests
```python
# 1. Create new flow JSON in fixtures/
# tests/fixtures/your_new_flow.json

# 2. Create test file
# tests/test_integration_your_domain.py

@pytest.fixture
def your_flow():
    """Load your domain-specific flow."""
    import pathlib
    flow_path = pathlib.Path(__file__).parent / "fixtures" / "your_new_flow.json"
    with open(flow_path) as f:
        flow_data = json.load(f)
    if flow_data.get('schema_version') != 'v2':
        flow_data['schema_version'] = 'v2'
    return Flow.model_validate(flow_data)

def test_your_domain_conversation(real_llm, your_flow):
    """Test realistic conversation for your domain."""
    compiled = compile_flow(your_flow)
    runner = FlowTurnRunner(compiled, real_llm)
    # ... implement conversation scenarios
```

## 🔍 Debugging & Monitoring

### Debug Output Analysis
```bash
# Enable debug mode
export DEBUG=true
pytest tests/test_comprehensive_dentist_flow.py -s

# Look for these patterns:
# [DEBUG] Available tools: [...]        # Tools LLM can choose from
# [DEBUG] User message: '...'           # What user said
# [DEBUG] LLM result: {...}             # LLM tool choice + reasoning  
# [DEBUG] Tool chosen: UpdateAnswersFlow # Final tool selected
# [DEBUG] Reasoning: ...                # Why LLM chose this tool
```

### Common Issues & Solutions

**❌ Test Skipped: "GOOGLE_API_KEY not configured"**
```bash
# Solution: Set up environment
echo 'GOOGLE_API_KEY=your_key_here' >> backend/.env
source backend/.env
```

**❌ API Rate Limit Exceeded**
```bash
# Solution: Increase delays or use staging API key
# In test file:
def rate_limit_delay():
    time.sleep(2.0)  # Increase delay
```

**❌ Wrong Tool Selected**
```bash
# Solution: Check LLM reasoning in debug output
# Look for: [DEBUG] Reasoning: ...
# Adjust test expectations or improve prompts
```

## 📊 Monitoring Test Quality

### Success Metrics to Track
```python
# Add to test output:
def analyze_conversation_quality(conversation_log):
    """Analyze conversation quality metrics."""
    tools_used = [turn.get("tool") for turn in conversation_log if turn.get("tool")]
    unique_tools = set(tools_used)
    
    metrics = {
        "total_turns": len(conversation_log),
        "tools_used": len(tools_used), 
        "unique_tools": len(unique_tools),
        "tool_accuracy": calculate_tool_accuracy(conversation_log),
        "completion_rate": 1.0 if conversation_log[-1].get("terminal") else 0.0
    }
    
    print(f"📊 Conversation Quality: {metrics}")
    return metrics
```

### Quality Thresholds
- **Tool Selection Accuracy**: > 90%
- **Conversation Completion**: > 95%
- **Tool Coverage**: All 8 tools tested
- **Realistic Flow**: > 5 different tools used in single conversation

## 🔄 Regular Testing Schedule

### Daily (Automated)
- ✅ Basic integration test (5 API calls, < 30 seconds)
- ✅ Code compilation and flow loading
- ✅ Tool schema validation

### Weekly (Before Releases)  
- ✅ Comprehensive dentist flow (50+ API calls, 3-5 minutes)
- ✅ All specific tool tests
- ✅ Multiple flow configurations

### Monthly (Full Validation)
- ✅ All integration tests with different LLM models
- ✅ Performance benchmarking
- ✅ Cost analysis and optimization

## 🎛️ Configuration Options

### Test Configuration
```python
# tests/integration_config.py
class IntegrationTestConfig:
    # API Settings
    llm_model = "gemini-2.5-flash-lite"  # Cost-effective
    rate_limit_delay = 1.0              # Seconds between calls
    max_retries = 3                     # API failure retries
    
    # Test Behavior  
    skip_slow_tests = False             # Skip comprehensive tests
    debug_output = False                # Show LLM reasoning
    save_conversation_logs = True       # For analysis
    
    # Quality Thresholds
    min_tool_accuracy = 0.90           # 90% tool selection accuracy
    max_api_calls_per_test = 100       # Budget control
    max_test_duration = 300            # 5 minutes max per test
```

### Easy Test Commands
```bash
# Create test runner script
# scripts/run_integration_tests.sh
#!/bin/bash
cd backend
source .venv/bin/activate
source .env

echo "🧪 Running LLM Integration Tests..."

# Quick validation
echo "📋 1. Basic integration test..."
pytest tests/test_integration_llm_flow.py::TestLLMFlowIntegration::test_basic_llm_integration_core_tools -q

# Comprehensive test (if time allows)
if [ "$1" == "--full" ]; then
    echo "🦷 2. Comprehensive dentist flow test..."
    pytest tests/test_comprehensive_dentist_flow.py -q
fi

echo "✅ Integration tests completed!"
```

```bash
# Make executable
chmod +x scripts/run_integration_tests.sh

# Quick test
./scripts/run_integration_tests.sh

# Full test
./scripts/run_integration_tests.sh --full
```

## 📈 Future Enhancements

### 1. **Multiple Flow Domains**
- Add restaurant reservation flow
- Add insurance claim flow  
- Add customer support flow
- Each with nested subpaths

### 2. **Advanced Testing Scenarios**
- Multi-language conversations (Portuguese + English)
- Error recovery and retry scenarios
- Performance testing with large flows
- Concurrent conversation handling

### 3. **Test Automation**
- Nightly regression testing
- Performance benchmarking  
- Cost tracking and alerts
- Quality metrics dashboard

## 🎯 Summary

**You now have a complete testing framework that:**

✅ **Validates real LLM behavior** with actual API calls
✅ **Tests complex nested flows** with realistic branching
✅ **Covers all flow tools** in natural conversation sequences  
✅ **Provides clear debugging** with detailed LLM reasoning
✅ **Scales for production** with cost controls and CI/CD integration
✅ **Maintains quality** with comprehensive monitoring

**To test in the future:** Just run the commands above! The tests are self-contained and will verify your entire LLM flow system continues working perfectly. 🚀
