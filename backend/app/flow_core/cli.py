from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from app.core.channel_adapter import CLIAdapter, ConversationalRewriter
from app.core.langchain_adapter import LangChainToolsLLM
from app.db.repository import get_active_tenants, get_flows_by_tenant
from app.db.session import db_session
from app.services.tenant_config_service import ProjectContext, TenantConfigService

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
    parser.add_argument(
        "--tenant",
        type=str,
        help="Use tenant from database. Provide tenant ID, channel identifier (e.g., 'whatsapp:+14155238886'), or 'default' for first tenant. Loads flow and communication style from database.",
    )
    parser.add_argument(
        "--flow-id",
        type=str,
        help="When using --tenant, select a specific flow by its flow_id. Defaults to the first active flow if omitted.",
    )
    args = parser.parse_args()

    # Load flow and tenant configuration
    flow, project_context = _load_flow_and_tenant(args)
    compiled = compile_flow(flow)

    print(f"Flow: {flow.id}")
    if project_context:
        print(f"[tenant] Using tenant: {project_context.tenant_id}")
        print(f"[tenant] Communication style: {'✓' if project_context.communication_style else '✗'}")
        print(f"[tenant] Project description: {'✓' if project_context.project_description else '✗'}")

    # Setup LLM and runner - LLM is always required
    if not args.llm:
        print("[error] LLM mode is required. Use --llm flag.")
        return

    # Ensure .env is loaded for API keys
    load_dotenv()
    
    # Determine provider based on model name
    if args.model.startswith(("gpt-", "o1-")):
        provider = "openai"
        if not os.environ.get("OPENAI_API_KEY"):
            print("[error] OPENAI_API_KEY not set. Required for GPT models.")
            return
    else:
        provider = "google_genai"
        if not os.environ.get("GOOGLE_API_KEY"):
            print("[error] GOOGLE_API_KEY not set. Required for Gemini models.")
            return

    # Initialize chat model with appropriate provider
    chat = init_chat_model(args.model, model_provider=provider)
    llm_client = LangChainToolsLLM(chat)
    runner = FlowTurnRunner(compiled, llm_client, strict_mode=False)
    rewrite_status = "on" if (not args.no_rewrite) else "off"
    delay_status = "off" if args.no_delays else "on"
    debug_status = "on" if args.debug else "off"
    print(
        f"[mode] LLM mode: model={args.model}, rewrite={rewrite_status}, delays={delay_status}, debug={debug_status}"
    )

    # Setup channel adapter and rewriter with tenant context
    from app.settings import is_development_mode
    # Use CLI debug flag OR unified development mode
    debug_enabled = args.debug or is_development_mode()
    cli_adapter = CLIAdapter(enable_delays=not args.no_delays, debug_mode=debug_enabled)
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

            # Build tool context for better naturalization
            tool_context = None
            # Prefer explicit tool_name from TurnResult and attach ack_message if engine provided it in metadata
            if getattr(result, "tool_name", None):
                tool_context = {"tool_name": result.tool_name}
                # FlowTurnRunner doesn't expose metadata directly; use final_response from engine if needed
                # Here, result.assistant_message is the base text; ack (if any) is for context only
            
            # Get current time in same format as conversation timestamps
            import datetime
            current_time = datetime.datetime.now().strftime("%H:%M")
            
            # Rewrite into multi-message format with tenant context
            # This ensures ALL messages (including first prompt) get tenant styling
            messages = rewriter.rewrite_message(
                display_text,
                chat_history,
                enable_rewrite=not args.no_rewrite,
                project_context=project_context,
                tool_context=tool_context,
                current_time=current_time
            )

            # Update conversation history with the rewritten version for future context
            if messages and not args.no_rewrite:
                # Combine all rewritten messages into a single string for history
                rewritten_content = " ".join(msg.get("text", "") for msg in messages if msg.get("text"))
                if rewritten_content.strip():
                    ctx.update_last_assistant_message(rewritten_content)

            # Display with debug info
            debug_info = None
            if debug_enabled:
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


def _load_flow_and_tenant(args) -> tuple[Flow, ProjectContext | None]:
    """Load flow and tenant configuration based on CLI arguments."""
    if not args.tenant:
        # Use file-based flow (original behavior)
        data = json.loads(args.json_path.read_text(encoding="utf-8"))
        # Keep original schema version (no forced conversion)
        flow = Flow.model_validate(data)
        return flow, None

    # Load from database using tenant
    with db_session() as session:
        tenant_service = TenantConfigService(session)
        project_context = None

        if args.tenant == "default":
            # Get first tenant
            tenants = get_active_tenants(session)
            if not tenants:
                print("[error] No tenants found in database. Create one first with seed_database.py")
                exit(1)
            project_context = tenant_service.get_project_context_by_tenant_id(tenants[0].id)
        elif args.tenant.startswith(("whatsapp:", "instagram:")):
            # Channel identifier
            project_context = tenant_service.get_project_context_by_channel_identifier(args.tenant)
        else:
            # Try as tenant ID
            try:
                tenant_id = UUID(args.tenant)
                project_context = tenant_service.get_project_context_by_tenant_id(tenant_id)
            except ValueError:
                print(f"[error] Invalid tenant identifier: {args.tenant}")
                print("Use: tenant_id, channel identifier (e.g., 'whatsapp:+14155238886'), or 'default'")
                exit(1)

        if not project_context:
            print(f"[error] Tenant not found: {args.tenant}")
            exit(1)

        # Get tenant's flows
        flows = get_flows_by_tenant(session, project_context.tenant_id)
        if not flows:
            print(f"[error] No flows found for tenant {project_context.tenant_id}")
            print("Create flows via the admin API or seed_database.py")
            exit(1)

        # Select flow: either by provided --flow-id or first active
        active_flows = [f for f in flows if f.is_active]
        if not active_flows:
            print(f"[error] No active flows found for tenant {project_context.tenant_id}")
            exit(1)

        selected_flow = None
        if getattr(args, "flow_id", None):
            for f in active_flows:
                if f.flow_id == args.flow_id:
                    selected_flow = f
                    break
            if not selected_flow:
                print(
                    f"[error] Flow with flow_id='{args.flow_id}' not found for tenant {project_context.tenant_id}"
                )
                print("Available active flows:")
                for f in active_flows:
                    print(f" - {f.flow_id} ({f.name})")
                exit(1)
        else:
            selected_flow = active_flows[0]

        flow_data = selected_flow.definition
        # Keep original schema version (no forced conversion)

        flow = Flow.model_validate(flow_data)
        print(f"[database] Loaded flow '{selected_flow.name}' (flow_id='{selected_flow.flow_id}') from database")
        return flow, project_context


if __name__ == "__main__":
    run_cli()
