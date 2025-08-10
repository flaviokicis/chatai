# Flow Core

Isolated core for authoring and executing conversational flows using a small JSON IR.

What you can do now:

- Author a flow in JSON (`backend/playground/flow_example.json`).
- Load and run it locally via the CLI without WhatsApp/Redis:
  python -m app.flow_core.cli backend/playground/flow_example.json

Concepts:

- Flow IR (`ir.py`): nodes (Question, Decision, Terminal), edges with optional guards.
- Compiler (`compiler.py`): validates references, orders edges, resolves guard refs.
- Engine (`engine.py`): executes the compiled flow in-process with a tiny state object.
- Guards (`guards.py`): safe, registry-based predicates; extend as needed.
- LangGraph adapter (`langgraph_adapter.py`): optional interop to LangGraph runtime.

State shape (engine):

- answers: dict[str, Any]
- current_node_id: str | None
- pending_field: str | None
- path policy fields: path_votes, active_path, path_locked (optional)

CLI demo:

- Prompts you at Question nodes; your input is recorded as the answer for that key.
- Decision nodes evaluate outgoing edges in priority order until a guard passes.
- Terminal node ends the run.

Notes:

- This is intentionally small, readable, and decoupled. Agents can adopt it incrementally.
- Extend by adding node kinds, guard functions, and policies without touching the engine.
