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
	. .venv/bin/activate && uv run pytest -q

lint:
	. .venv/bin/activate && uv run ruff check .

lint-fix:
	. .venv/bin/activate && uv run ruff check --fix .

lint-fix-unsafe:
	. .venv/bin/activate && uv run ruff check --fix --unsafe-fixes .

fmt:
	. .venv/bin/activate && uv run ruff format .

typecheck:
	. .venv/bin/activate && uv run mypy --config-file pyproject.toml app tests

ci: lint fmt typecheck test

# Render Mermaid HTML from a question graph JSON
# Usage: make render-graph GRAPH=playground/some_graph.json
.PHONY: render-graph  # Deprecated alias to kroki
render-graph: render-graph-kroki

.PHONY: render-graph-kroki
render-graph-kroki:
	@if [ -z "$(GRAPH)" ]; then echo "GRAPH=<path/to/json> is required" && exit 1; fi
	. .venv/bin/activate && uv run python -c 'import sys, pathlib, json; from app.utils.graphviz import render_html_mermaid_via_kroki; p=sys.argv[1]; payload=json.load(open(p)); html=render_html_mermaid_via_kroki(payload, pathlib.Path(p).stem); out=pathlib.Path(p).with_suffix(".kroki.html"); out.write_text(html, encoding="utf-8"); print(out.resolve())' $(GRAPH)


