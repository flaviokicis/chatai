from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from app import dev_config
from app.core.langchain_adapter import LangChainToolsLLM
from app.core.naturalize import naturalize_prompt

from .compiler import compile_flow
from .engine import LLMFlowEngine
from .ir import Flow
from .llm_responder import LLMFlowResponder
from .responders import ManualResponder


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
    # Normalize legacy payloads to current schema version
    if isinstance(data, dict) and data.get("schema_version") != "v2":
        data["schema_version"] = "v2"
    flow = Flow.model_validate(data)
    compiled = compile_flow(flow)

    print(f"Flow: {flow.id}")

    # Setup LLM and responder
    llm_client = None
    if args.llm:
        # Ensure .env is loaded so GOOGLE_API_KEY is available for Gemini
        load_dotenv()
        if not os.environ.get("GOOGLE_API_KEY"):
            print("[warn] GOOGLE_API_KEY not set; falling back to manual responder.")
            args.llm = False

    if args.llm:
        # Initialize Gemini via LangChain init_chat_model to reuse existing adapter
        chat = init_chat_model(args.model, model_provider="google_genai")
        llm_client = LangChainToolsLLM(chat)
        responder = LLMFlowResponder(llm_client)
        rewrite_status = "on" if (not args.no_rewrite) else "off"
        print(f"[mode] LLM mode: model={args.model}, rewrite={rewrite_status}")
    else:
        responder = ManualResponder()
        print("[mode] Manual mode (no LLM)")

    # Create engine and initialize context
    engine = LLMFlowEngine(compiled, llm_client, strict_mode=not args.llm)
    ctx = engine.initialize_context()

    while True:
        # Process with engine
        response = engine.process(ctx)

        if response.kind == "terminal":
            print(f"[terminal] {response.message}")
            break

        display_text = response.message or ""
        if args.llm and (not args.no_rewrite) and llm_client is not None:
            display_text = naturalize_prompt(llm_client, display_text)

        print(f"[prompt:{response.node_id}] {display_text}")

        # Get user input
        user = input("> ").strip()
        if user == ":quit":
            break

        if args.llm and responder:
            # Use LLM responder
            node = compiled.nodes.get(ctx.current_node_id) if ctx.current_node_id else None
            allowed_values: list[str] | None = None
            if node is not None:
                # Get allowed values from QuestionNode
                vals = getattr(node, "allowed_values", None)
                if isinstance(vals, list) and all(isinstance(v, str) for v in vals):
                    allowed_values = vals
                else:
                    # Backward-compat: read from meta.allowed_values if present
                    meta = getattr(node, "meta", None)
                    if isinstance(meta, dict):
                        mvals = meta.get("allowed_values")
                        if isinstance(mvals, list) and all(isinstance(v, str) for v in mvals):
                            allowed_values = mvals  # type: ignore[assignment]

            # Use LLMFlowResponder
            r = responder.respond(
                display_text,
                ctx.pending_field,
                ctx,
                user,
                allowed_values,
            )

            # Debug logging
            if dev_config.debug:
                print(f"[DEBUG] Tool chosen: {r.tool_name}")
                print(f"[DEBUG] Updates: {r.updates}")
                print(f"[DEBUG] Metadata: {r.metadata}")
                print(f"[DEBUG] Current answers: {ctx.answers}")
                print(f"[DEBUG] Pending field: {ctx.pending_field}")

            # Apply updates to context
            for k, v in r.updates.items():
                ctx.answers[k] = v

            # Show assistant message for all tools, including confirmations
            if r.message:
                print(f"[assistant] {r.message}")

            # Forward responder outcome to engine; let engine handle all tools uniformly
            engine_event: dict[str, object] = {"tool_name": r.tool_name or ""}
            if ctx.pending_field and ctx.pending_field in r.updates:
                engine_event["answer"] = r.updates[ctx.pending_field]
            if r.message:
                engine_event["ack_message"] = r.message
            if r.metadata:
                engine_event.update(r.metadata)
            engine.process(ctx, user, engine_event)
        # Manual mode - directly update context
        elif ctx.pending_field and user:
            ctx.answers[ctx.pending_field] = user
            # Process the answer with engine
            engine.process(ctx, user, {"answer": user})


if __name__ == "__main__":
    run_cli()
