# 🧪 Testing Quick Reference

## LLM Integration Tests

### ⚡ Quick Test (30 seconds)
```bash
make test-integration
# OR
./scripts/test_llm_integration.sh
```

### 🚀 Full Test Suite (3-5 minutes)  
```bash
make test-integration-full
# OR  
./scripts/test_llm_integration.sh --full
```

### 🐛 Debug Mode
```bash
./scripts/test_llm_integration.sh --debug
```

## Test Categories

| Test | Purpose | API Calls | Duration |
|------|---------|-----------|----------|
| **Basic Integration** | Core tools verification | ~5 | 30s |
| **Comprehensive Dentist** | Realistic conversation | ~30 | 3-5m |
| **Specific Tools** | Individual tool testing | ~15 | 1-2m |

## Test Markers

```bash
# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Run only LLM tests  
pytest -m llm

# Run unit tests only
pytest -m "not integration"
```

## Environment Requirements

```bash
# Required in .env:
GOOGLE_API_KEY=your_key_here
LLM_MODEL=gemini-2.5-flash-lite
```

## What Gets Tested

✅ **All Flow Tools**: UpdateAnswersFlow, ClarifyQuestion, PathCorrection, RequestHumanHandoff, RevisitQuestion, UnknownAnswer, SkipQuestion, RestartConversation

✅ **Complex Flows**: 4 main paths × 3 subpaths = 12 unique conversation routes

✅ **Real Conversations**: Natural Portuguese interactions with intelligent tool selection

✅ **Error Scenarios**: Clarifications, corrections, escalations, unknowns

✅ **Production Readiness**: End-to-end validation with actual LLM calls

## 🎯 Success Criteria

- **Tool Selection**: >90% accuracy
- **Conversation Completion**: >95% success rate  
- **All Tools Tested**: 8/8 tools exercised
- **Complex Navigation**: Nested subpaths working
- **Portuguese Quality**: Natural conversation flow

## 🚨 When Tests Fail

1. **Check API Key**: `echo $GOOGLE_API_KEY`
2. **Check Rate Limits**: Add delays if hitting limits
3. **Check Debug Output**: Run with `--debug` flag
4. **Check LLM Reasoning**: Look at `[DEBUG] Reasoning:` output
5. **Check Flow Definition**: Validate JSON flow structure

## 📊 Monitoring

The tests provide detailed output showing:
- Every tool selection decision
- LLM reasoning for each choice
- Complete conversation transcripts
- Tool usage statistics
- Flow navigation paths taken

Perfect for verifying your LLM conversation system continues working as expected! 🚀
