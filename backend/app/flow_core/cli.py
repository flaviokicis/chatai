from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from app.core.channel_adapter import CLIAdapter, ConversationalRewriter
from app.core.langchain_adapter import LangChainToolsLLM

from .compiler import compile_flow
from .ir import Flow
from .runner import FlowTurnRunner


def _playground_flow_path() -> Path:
    """Return backend/playground/flow_example.json resolved from this file."""
    # __file__ = backend/app/flow_core/cli.py -> parents[2] = backend
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "playground" / "flow_example.json"


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Run a Flow IR JSON interactively")
    parser.add_argument(
        "json_path",
        nargs="?",
        type=Path,
        default=_playground_flow_path(),
        help="Path to flow JSON file (default: backend/playground/flow_example.json)",
    )
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
    parser.add_argument(
        "--no-delays",
        action="store_true",
        help="Disable delays between multi-messages for faster interaction",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output showing internal flow state",
    )
    args = parser.parse_args()

    data = json.loads(args.json_path.read_text(encoding="utf-8"))
    # Normalize legacy payloads to current schema version
    if isinstance(data, dict) and data.get("schema_version") != "v2":
        data["schema_version"] = "v2"
    flow = Flow.model_validate(data)
    compiled = compile_flow(flow)

    print(f"Flow: {flow.id}")

    # Setup LLM and runner
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
        runner = FlowTurnRunner(compiled, llm_client, strict_mode=False)
        rewrite_status = "on" if (not args.no_rewrite) else "off"
        delay_status = "off" if args.no_delays else "on"
        debug_status = "on" if args.debug else "off"
        print(
            f"[mode] LLM mode: model={args.model}, rewrite={rewrite_status}, delays={delay_status}, debug={debug_status}"
        )
    else:
        runner = FlowTurnRunner(compiled, None, strict_mode=True)
        print("[mode] Manual mode (no LLM)")

    # Setup channel adapter and rewriter
    cli_adapter = CLIAdapter(enable_delays=not args.no_delays, debug_mode=args.debug)
    rewriter = ConversationalRewriter(llm_client if not args.no_rewrite else None)

    # Initialize context
    ctx = runner.initialize_context()

    # Start like WhatsApp: wait for first user input; do not auto-prompt
    while True:
        user = input("> ").strip()
        if user == ":quit":
            break
        result = runner.process_turn(ctx, user)

        # Handle terminal/escalate
        if result.terminal:
            print(f"[terminal] {result.assistant_message}")
            break
        if result.escalate:
            print(f"[escalate] {result.assistant_message}")
            break

        # Display assistant message via shared rewriter system
        display_text = result.assistant_message or ""
        if display_text:
            # Build chat history from flow context
            chat_history = rewriter.build_chat_history(
                flow_context_history=getattr(ctx, "history", None)
            )

            # Rewrite into multi-message format
            messages = rewriter.rewrite_message(
                display_text, chat_history, enable_rewrite=not args.no_rewrite
            )

            # Display with debug info
            debug_info = None
            if args.debug:
                debug_info = {
                    "node_id": ctx.current_node_id,
                    "pending_field": getattr(ctx, "pending_field", None),
                    "answers_count": len(getattr(ctx, "answers", {})),
                    "turn_count": getattr(ctx, "turn_count", 0),
                    "message_count": len(messages),
                }

            cli_adapter.display_messages(
                messages, prefix=f"[prompt:{ctx.current_node_id}] ", debug_info=debug_info
            )

        # Next loop waits for next user input (no auto-prompt)


if __name__ == "__main__":
    run_cli()
