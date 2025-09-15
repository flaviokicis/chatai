.PHONY: install dev test lint lint-fix fmt typecheck validate validate-quick ci

PROJECT_DIR := $(shell pwd)
APP := app.main:app
HOST ?= 0.0.0.0
PORT ?= 8080
CONFIG ?= ./config.local.json

install:
	uv venv
	. .venv/bin/activate && uv sync

dev:
	. .venv/bin/activate && CONFIG_JSON_PATH=$(CONFIG) uvicorn $(APP) --reload --host $(HOST) --port $(PORT)

test:
	. .venv/bin/activate && PYTHONPATH=. uv run pytest -q -m "not integration and not llm"

# Run basic LLM integration tests (requires GOOGLE_API_KEY)
.PHONY: test-integration
test-integration:
	. .venv/bin/activate && source .env && PYTHONPATH=. uv run pytest tests/test_integration_llm_flow.py::TestLLMFlowIntegration::test_basic_llm_integration_core_tools -v

# Run comprehensive LLM integration tests (many API calls, ~3-5 minutes)
.PHONY: test-integration-full
test-integration-full:
	. .venv/bin/activate && source .env && PYTHONPATH=. GOOGLE_API_KEY="$$GOOGLE_API_KEY" uv run pytest tests/test_comprehensive_dentist_flow.py tests/test_integration_specific_tools.py -m "integration and llm" -v -s

# Run all integration tests with proper setup
.PHONY: test-integration-all
test-integration-all:
	./scripts/test_llm_integration.sh --full

lint:
	. .venv/bin/activate && uv run ruff check .

lint-fix:
	. .venv/bin/activate && uv run ruff check --fix .

lint-fix-unsafe:
	. .venv/bin/activate && uv run ruff check --fix --unsafe-fixes .

fmt:
	. .venv/bin/activate && uv run ruff format .

typecheck:
	. .venv/bin/activate && PYTHONPATH=. uv run mypy --config-file pyproject.toml app tests

# Pre-flight validation - catches issues before runtime  
validate:
	@echo "🚀 Pre-flight Validation"
	@echo "========================"
	@echo ""
	@echo "\033[1;33m1. Running Ruff linter (critical errors only)...\033[0m"
	@RUFF_OUTPUT=$$(. .venv/bin/activate && ruff check app/ --quiet 2>&1 || true); \
	if echo "$$RUFF_OUTPUT" | grep -q "F401\|F821\|E999\|W292\|F541"; then \
		echo "\033[0;31m❌ Critical Ruff errors found:\033[0m"; \
		echo "$$RUFF_OUTPUT" | grep -E "(F401|F821|E999|W292|F541)"; \
		echo "\033[0;31mRun 'make lint-fix' to auto-fix these critical issues\033[0m"; \
		exit 1; \
	else \
		echo "\033[0;32m✅ Ruff: No critical errors (style warnings ignored)\033[0m"; \
	fi
	@echo ""
	@echo "\033[1;33m2. Checking function signatures and critical type errors with MyPy...\033[0m"
	@MYPY_OUTPUT=$$(. .venv/bin/activate && mypy app/flow_core/whatsapp_cli.py app/db/repository.py app/services/message_logging_service.py app/core/flow_processor.py app/flow_core/services/responder.py --ignore-missing-imports --no-error-summary 2>&1 || true); \
	if echo "$$MYPY_OUTPUT" | grep -q "Unexpected keyword argument\|Missing named argument"; then \
		echo "\033[0;31m❌ Function signature mismatches found:\033[0m"; \
		echo "$$MYPY_OUTPUT" | grep -E "(Unexpected keyword argument|Missing named argument)" -A1 -B1 | head -20; \
		echo "\033[0;31mFix these before running to avoid runtime errors!\033[0m"; \
		exit 1; \
	elif echo "$$MYPY_OUTPUT" | grep -E "ToolExecutionResult.*has no attribute" | grep -E "(messages|assistant_message|external_action_successful|tool_name)" > /dev/null; then \
		echo "\033[0;31m❌ ToolExecutionResult attribute errors found:\033[0m"; \
		echo "$$MYPY_OUTPUT" | grep -E "ToolExecutionResult.*has no attribute" -A1 -B1 | head -20; \
		echo "\033[0;31mFix these attribute access issues!\033[0m"; \
		exit 1; \
	else \
		echo "\033[0;32m✅ MyPy: No critical type errors\033[0m"; \
	fi
	@echo ""
	@echo "\033[1;33m3. Checking for syntax errors in recently modified files...\033[0m"
	@MODIFIED_FILES=$$(find app/ -name "*.py" -mtime -1 2>/dev/null | head -10); \
	if [ ! -z "$$MODIFIED_FILES" ]; then \
		for file in $$MODIFIED_FILES; do \
			if ! . .venv/bin/activate && python -m py_compile "$$file" 2>/dev/null; then \
				echo "\033[0;31m❌ Syntax error in $$file\033[0m"; \
				. .venv/bin/activate && python -m py_compile "$$file"; \
				exit 1; \
			fi; \
		done; \
	fi
	@echo "\033[0;32m✅ No syntax errors in recently modified files\033[0m"
	@echo ""
	@echo "\033[1;33m4. Checking critical imports...\033[0m"
	@if . .venv/bin/activate && python -c "from app.flow_core.whatsapp_cli import WhatsAppSimulatorCLI; from app.db.repository import create_message" 2>/dev/null; then \
		echo "\033[0;32m✅ Critical imports working\033[0m"; \
	else \
		echo "\033[0;31m❌ Import errors detected\033[0m"; \
		. .venv/bin/activate && python -c "from app.flow_core.whatsapp_cli import WhatsAppSimulatorCLI; from app.db.repository import create_message"; \
		exit 1; \
	fi
	@echo ""
	@echo "\033[1;33m5. Validating database functions...\033[0m"
	@if . .venv/bin/activate && python -c "import inspect; from app.db.repository import create_message; sig = inspect.signature(create_message); params = list(sig.parameters.keys()); required = ['session', 'tenant_id', 'channel_instance_id', 'thread_id', 'contact_id', 'text']; missing = [p for p in required if p not in params]; exit(1) if missing else print('✅ create_message signature valid')"; then \
		echo "\033[0;32m✅ Database function signatures valid\033[0m"; \
	else \
		echo "\033[0;31m❌ Database function signature issues detected\033[0m"; \
		exit 1; \
	fi
	@echo ""
	@echo "\033[1;33m6. Checking for JSON serialization issues...\033[0m"
	@if . .venv/bin/activate && python -c "import re, pathlib; content = pathlib.Path('app/flow_core/services/responder.py').read_text(); matches = re.findall(r'context\.is_complete[^(]', content); exit(1) if matches else print('✅ No method serialization issues')" 2>/dev/null; then \
		echo "\033[0;32m✅ No JSON serialization issues\033[0m"; \
	else \
		echo "\033[0;31m❌ JSON serialization issue: context.is_complete should be context.is_complete()\033[0m"; \
		exit 1; \
	fi
	@echo ""
	@echo "\033[1;33m7. Validating flow compilation and edge attributes...\033[0m"
	@if . .venv/bin/activate && python -c "from app.flow_core.compiler import CompiledEdge; e = CompiledEdge(source='a', target='b'); hasattr(e, 'condition_description') or exit(1); print('✅ CompiledEdge attributes valid')"; then \
		echo "\033[0;32m✅ Flow compilation types valid\033[0m"; \
	else \
		echo "\033[0;31m❌ Flow compilation issues detected\033[0m"; \
		exit 1; \
	fi
	@echo ""
	@echo "\033[0;32m========================\033[0m"
	@echo "\033[0;32m✅ All validations passed!\033[0m" 
	@echo "\033[0;32m========================\033[0m"
	@echo ""
	@echo "You can now safely run:"
	@echo "  \033[1;33mmake whatsapp-cli\033[0m"

# Quick validation - just function signatures and imports (faster)
validate-quick:
	@echo "⚡ Quick Validation"
	@echo "=================="
	@echo ""
	@echo "\033[1;33mChecking function signatures...\033[0m"
	@MYPY_OUTPUT=$$(. .venv/bin/activate && mypy app/flow_core/whatsapp_cli.py app/db/repository.py --ignore-missing-imports --no-error-summary 2>&1 || true); \
	if echo "$$MYPY_OUTPUT" | grep -q "Unexpected keyword argument\|Missing named argument"; then \
		echo "\033[0;31m❌ Function signature issues found:\033[0m"; \
		echo "$$MYPY_OUTPUT" | grep -E "(Unexpected keyword argument|Missing named argument)" -A1 -B1; \
		exit 1; \
	else \
		echo "\033[0;32m✅ Function signatures OK\033[0m"; \
	fi
	@echo "\033[1;33mChecking imports...\033[0m"
	@if . .venv/bin/activate && python -c "from app.flow_core.whatsapp_cli import WhatsAppSimulatorCLI; from app.db.repository import create_message" 2>/dev/null; then \
		echo "\033[0;32m✅ Imports OK\033[0m"; \
	else \
		echo "\033[0;31m❌ Import errors\033[0m"; \
		exit 1; \
	fi
	@echo "\033[0;32m✅ Quick validation passed!\033[0m"

ci: lint fmt typecheck validate test

# Danger: Drop and recreate all tables (useful after UUID migration)
.PHONY: reset-db
reset-db:
	. .venv/bin/activate && uv run python -c "from app.db.models import *; from app.db.base import Base; from app.db.session import get_engine; eng=get_engine(); Base.metadata.drop_all(bind=eng); Base.metadata.create_all(bind=eng); print('✅ Dropped and recreated all tables')"

# Seed the database with example tenant, channel, and flow
.PHONY: seed-db
seed-db:
	. .venv/bin/activate && uv run python seed_database.py

# Complete database setup: reset tables + seed data (useful for development)
.PHONY: setup-db
setup-db: reset-db seed-db

# Run the Flow Core CLI (manual mode by default)
.PHONY: flow
flow:
	. .venv/bin/activate && uv run python -m app.flow_core.cli ./playground/flow_example.json

# Run the Flow Core CLI with LLM (GPT-5) filling answers via tools
.PHONY: flow-llm
flow-llm:
	. .venv/bin/activate && uv run python -m app.flow_core.cli --llm --model gpt-5 --tenant 068b37cd-c090-710d-b0b6-5ca37c2887ff

.PHONY: flow-llm-raw
flow-llm-raw:
	. .venv/bin/activate && uv run python -m app.flow_core.cli --llm --no-rewrite --model gpt-5 --tenant 068b37cd-c090-710d-b0b6-5ca37c2887ff

# Run the async Flow CLI - allows typing while processing (non-blocking)
.PHONY: flow-async
flow-async:
	. .venv/bin/activate && uv run python -m app.flow_core.cli_async ./playground/fluxo_luminarias.json --model gpt-5

# Run the unified Flow CLI - uses exact same FlowProcessor as WhatsApp (with cancellation/aggregation)
.PHONY: flow-unified
flow-unified:
	. .venv/bin/activate && uv run python -m app.flow_core.cli_unified ./playground/fluxo_luminarias.json --model gpt-5

# Run WhatsApp CLI simulator with production infrastructure
.PHONY: whatsapp-cli
whatsapp-cli:
	. .venv/bin/activate && uv run python -m app.flow_core.whatsapp_cli --phone +15550489424

# Run the Flow Core CLI with LLM using the JSON file (for testing without database)
.PHONY: flow-llm-file
flow-llm-file:
	. .venv/bin/activate && uv run python -m app.flow_core.cli --llm --model gpt-5 ./playground/flow_example.json

# Render Mermaid HTML from a question graph JSON
# Usage: make render-graph GRAPH=playground/some_graph.json
.PHONY: render-graph  # Deprecated alias to kroki
render-graph: render-graph-kroki

.PHONY: render-graph-kroki
render-graph-kroki:
	@echo "Graph rendering via Kroki is not available in this refactor (QuestionGraph removed)."


