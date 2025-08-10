from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from app.core.langchain_adapter import LangChainToolsLLM
from app.core.naturalize import clarify_and_reask, naturalize_prompt

from .compiler import compile_flow
from .engine import Engine
from .ir import Flow
from .responders import CompositeResponder, LLMResponder, ManualResponder


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Run a Flow IR JSON interactively")
    parser.add_argument("json_path", type=Path, help="Path to flow JSON file")
    parser.add_argument("--llm", action="store_true", help="Use LLM to fill answers")
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-flash",
        help="Chat model for tool calling (default: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--rewrite-model",
        type=str,
        default="gemini-2.5-flash-lite",
        help="Model used for rewrites (not used in CLI, reserved)",
    )
    parser.add_argument(
        "--no-rewrite",
        action="store_true",
        help="Do not use rewrite LLM; show raw prompt text",
    )
    args = parser.parse_args()

    data = json.loads(args.json_path.read_text(encoding="utf-8"))
    flow = Flow.model_validate(data)
    compiled = compile_flow(flow)
    eng = Engine(compiled)
    state = eng.start()

    print(f"Flow: {flow.id}")
    # Decide responder
    llm_client = None
    if args.llm:
        # Ensure .env is loaded so GOOGLE_API_KEY is available for Gemini
        load_dotenv()
        if not os.environ.get("GOOGLE_API_KEY"):
            print("ERROR: GOOGLE_API_KEY is not set in environment or .env file.")
            raise SystemExit(1)
        # Initialize Gemini via LangChain init_chat_model to reuse existing adapter
        chat = init_chat_model(args.model, model_provider="google_genai")
        llm_client = LangChainToolsLLM(chat)
        responder = CompositeResponder(LLMResponder(llm_client), ManualResponder())
    else:
        responder = ManualResponder()

    while True:
        out = eng.step(state)
        if out.kind == "terminal":
            print(f"[terminal] {out.message}")
            break
        display_text = out.message or ""
        if not args.no_rewrite:
            if llm_client is None:
                # initialize a minimal client just for rewrite
                load_dotenv()
                if not os.environ.get("GOOGLE_API_KEY"):
                    print("ERROR: GOOGLE_API_KEY is not set in environment or .env file.")
                    raise SystemExit(1)
                chat = init_chat_model(args.model, model_provider="google_genai")
                llm_client = LangChainToolsLLM(chat)
            display_text = naturalize_prompt(llm_client, display_text)
        print(f"[prompt:{out.node_id}] {display_text}")
        # In LLM mode, we still allow user to supply a message; otherwise, they can press enter
        user = input("> ").strip()
        if user == ":quit":
            break
        # If the node encodes allowed path values, pass them down to the responder
        node = compiled.nodes.get(state.current_node_id) if state.current_node_id else None
        allowed_values: list[str] | None = None
        if node and isinstance(getattr(node, "meta", {}), dict):
            meta = node.meta
            vals = meta.get("allowed_values") if isinstance(meta, dict) else None
            if isinstance(vals, list) and all(isinstance(v, str) for v in vals):
                allowed_values = vals  # type: ignore[assignment]
        # Assemble a small text history for the LLM (oldest to newest)
        # For the CLI, keep it local per run
        history: list[dict[str, str]] = []
        # We could persist/display prior turns; for now, include only the last assistant prompt
        history.append({"role": "assistant", "content": display_text})
        r = responder.respond(
            out.message or "",
            state.pending_field,
            state.answers,
            user,
            allowed_values,
            history,
        )
        # Apply updates
        for k, v in r.updates.items():
            state.answers[k] = v
        # Feed last answer value as event for guard evaluation if single-field update
        if state.pending_field and state.pending_field in r.updates:
            # Pass allowed_values and tool to allow guard/context-sensitive behavior
            eng.step(
                state,
                {
                    "answer": r.updates[state.pending_field],
                    "allowed_values": allowed_values or [],
                    "tool_name": r.tool_name,
                },
            )
        # Show assistant message if provided by the LLM responder
        if r.assistant_message:
            print(f"[assistant] {r.assistant_message}")
        # If it's a clarification and we are rewriting, enrich the prompt with a brief acknowledgement
        elif (not args.no_rewrite) and llm_client is not None and r.tool_name == "UnknownAnswer":
            followup = clarify_and_reask(llm_client, display_text, user)
            print(f"[prompt:{out.node_id}] {followup}")


if __name__ == "__main__":
    run_cli()
