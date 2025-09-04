.PHONY: install dev test lint lint-fix fmt typecheck ci

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

ci: lint fmt typecheck test

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
	. .venv/bin/activate && uv run python -m app.flow_core.cli --llm --model gpt-5 --tenant default

.PHONY: flow-llm-raw
flow-llm-raw:
	. .venv/bin/activate && uv run python -m app.flow_core.cli --llm --no-rewrite --model gpt-5 --tenant default

# Run the async Flow CLI - allows typing while processing (non-blocking)
.PHONY: flow-async
flow-async:
	. .venv/bin/activate && uv run python -m app.flow_core.cli_async ./playground/fluxo_luminarias.json --model gpt-5

# Run the unified Flow CLI - uses exact same FlowProcessor as WhatsApp (with cancellation/aggregation)
.PHONY: flow-unified
flow-unified:
	. .venv/bin/activate && uv run python -m app.flow_core.cli_unified ./playground/fluxo_luminarias.json --model gpt-5

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


