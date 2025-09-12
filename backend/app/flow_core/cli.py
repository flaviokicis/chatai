from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from app.core.langchain_adapter import LangChainToolsLLM
from app.db.repository import get_active_tenants, get_flows_by_tenant
from app.db.session import db_session
from app.services.tenant_config_service import ProjectContext, TenantConfigService

from .compiler import compile_flow
from .ir import Flow
from .runner import FlowTurnRunner
from .state import FlowContext


def _playground_flow_path() -> Path:
    """Return backend/playground/flow_example.json resolved from this file."""
    # __file__ = backend/app/flow_core/cli.py -> parents[2] = backend
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "playground" / "flow_example.json"


class SimpleCLIAdapter:
    """Simple CLI adapter to replace the deleted CLIAdapter."""
    
    def __init__(self):
        pass
    
    def print_message(self, text: str) -> None:
        """Print a message to the console."""
        print(f"🤖 {text}")
    
    def print_messages(self, messages: list[dict[str, any]]) -> None:
        """Print multiple messages with delays."""
        for msg in messages:
            delay_ms = msg.get("delay_ms", 0)
            if delay_ms > 0:
                print(f"   [delay: {delay_ms}ms]")
            self.print_message(msg["text"])
    
    def get_user_input(self, prompt: str = "You: ") -> str:
        """Get user input from the console."""
        try:
            return input(prompt).strip()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            exit(0)
    
    def print_status(self, message: str) -> None:
        """Print a status message."""
        print(f"📊 {message}")
    
    def print_error(self, message: str) -> None:
        """Print an error message."""
        print(f"❌ {message}")


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
        default="gpt-5",
        help="Chat model for tool calling (default: gpt-5)",
    )
    parser.add_argument(
        "--rewrite-model",
        type=str,
        default="gpt-5",
        help="Model used for rewrites (not used in CLI, reserved)",
    )
    parser.add_argument(
        "--no-rewrite",
        action="store_true",
        help="Disable conversational rewriting (raw GPT responses)",
    )
    parser.add_argument(
        "--tenant",
        type=str,
        help="Tenant ID to load flows from database",
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Initialize CLI adapter
    cli_adapter = SimpleCLIAdapter()

    # Initialize LLM if requested
    llm_client = None
    if args.llm:
        try:
            # Set up API keys based on model
            if args.model.startswith("gpt"):
                if not os.getenv("OPENAI_API_KEY"):
                    cli_adapter.print_error("OPENAI_API_KEY environment variable required for GPT models")
                    return
                chat_model = init_chat_model(args.model, model_provider="openai")
            else:
                if not os.getenv("GOOGLE_API_KEY"):
                    cli_adapter.print_error("GOOGLE_API_KEY environment variable required for non-OpenAI models")
                    return
                chat_model = init_chat_model(args.model, model_provider="google")
            
            llm_client = LangChainToolsLLM(chat_model)
            cli_adapter.print_status(f"LLM initialized: {args.model}")
        except Exception as e:
            cli_adapter.print_error(f"Failed to initialize LLM: {e}")
            return

    # Load flow
    flow_json = None
    compiled_flow = None
    
    if args.tenant:
        # Load from database
        cli_adapter.print_status(f"Loading flows from database for tenant: {args.tenant}")
        try:
            with db_session() as session:
                tenants = get_active_tenants(session)
                tenant_found = False
                for tenant in tenants:
                    if str(tenant.id) == args.tenant:
                        tenant_found = True
                        flows = get_flows_by_tenant(session, tenant.id)
                        if flows:
                            # Use the first flow for now
                            flow_data = flows[0]
                            flow_json = flow_data.definition
                            cli_adapter.print_status(f"Loaded flow: {flow_data.name} (ID: {flow_data.id})")
                        else:
                            cli_adapter.print_error(f"No flows found for tenant {args.tenant}")
                            return
                        break
                
                if not tenant_found:
                    cli_adapter.print_error(f"Tenant '{args.tenant}' not found")
                    return
        except Exception as e:
            cli_adapter.print_error(f"Failed to load flow from database: {e}")
            return
    else:
        # Load from JSON file
        if not args.json_path.exists():
            cli_adapter.print_error(f"Flow file not found: {args.json_path}")
            return

        try:
            with open(args.json_path, "r", encoding="utf-8") as f:
                flow_json = json.load(f)
            cli_adapter.print_status(f"Loaded flow from: {args.json_path}")
        except Exception as e:
            cli_adapter.print_error(f"Failed to load flow file: {e}")
            return

    # Compile flow
    try:
        flow = Flow.model_validate(flow_json)
        compiled_flow = compile_flow(flow)
        flow_name = flow.metadata.name if flow.metadata else compiled_flow.id
        cli_adapter.print_status(f"Flow compiled successfully: {flow_name}")
    except Exception as e:
        cli_adapter.print_error(f"Failed to compile flow: {e}")
        return

    # Initialize runner
    if not llm_client:
        cli_adapter.print_error("LLM is required for the current flow system. Use --llm flag.")
        return
    
    runner = FlowTurnRunner(compiled_flow, llm_client)
    context = runner.initialize_context()
    
    # Project context (optional)
    project_context = None
    if args.tenant:
        try:
            from uuid import UUID
            with db_session() as session:
                config_service = TenantConfigService(session)
                tenant_uuid = UUID(args.tenant)
                project_context = config_service.get_project_context_by_tenant_id(tenant_uuid)
                if project_context:
                    cli_adapter.print_status("Loaded project context from tenant config")
        except Exception as e:
            cli_adapter.print_status(f"Could not load project context: {e}")

    # Main conversation loop
    cli_adapter.print_status("Starting conversation. Type 'quit' or 'exit' to stop, Ctrl+C to interrupt.")
    cli_adapter.print_status(f"Flow: {flow_name}")
    if project_context:
        cli_adapter.print_status(f"Project context loaded for tenant: {project_context.tenant_id}")
    
    # Show initial state
    print("\n" + "="*60)
    print("📊 INITIAL STATE:")
    print(f"   Starting node: {context.current_node_id}")
    print(f"   No answers collected yet")
    print("="*60)
    print()

    turn_count = 0
    while True:
        turn_count += 1
        
        # Get user input
        if turn_count == 1:
            # First turn - start the conversation
            user_input = cli_adapter.get_user_input("Start conversation: ")
        else:
            user_input = cli_adapter.get_user_input()
        
        if user_input.lower() in ["quit", "exit", "bye"]:
            cli_adapter.print_status("Goodbye!")
            break
        
        if not user_input:
            continue

        # Process the turn (CLI users are always admin)
        try:
            result = runner.process_turn(context, user_input, project_context, is_admin=True)
            
            # Check if flow modification was requested
            if hasattr(result, 'metadata') and result.metadata and result.metadata.get('flow_modification_requested'):
                print("\n" + "="*60)
                print("📝 FLOW MODIFICATION REQUESTED")
                print("="*60)
                
                instruction = result.metadata.get('modification_instruction', '')
                mod_type = result.metadata.get('modification_type', 'general')
                
                print(f"Type: {mod_type}")
                print(f"Instruction: {instruction[:200]}..." if len(instruction) > 200 else f"Instruction: {instruction}")
                print("\n⚠️  Note: Flow modification is not yet implemented in CLI mode.")
                print("    Use the web interface or API for live flow modifications.")
                print("="*60 + "\n")
            
            # Display response
            if result.messages:
                cli_adapter.print_messages(result.messages)
            elif result.assistant_message:
                cli_adapter.print_message(result.assistant_message)
            
            # Show debug info
            if result.tool_name:
                print(f"   [Tool: {result.tool_name}]")
                
                # Show specific actions if available
                if hasattr(result, 'metadata') and result.metadata:
                    if 'actions' in result.metadata:
                        actions = result.metadata['actions']
                        print(f"   [Actions: {', '.join(actions)}]")
                    
                    # Also check in the responder output metadata
                    if hasattr(result, 'responder_metadata'):
                        if 'actions' in result.responder_metadata:
                            actions = result.responder_metadata['actions']
                            print(f"   [Actions (from responder): {', '.join(actions)}]")
                    
                    # Show flow modification details if present
                    if result.metadata.get('flow_modification_requested'):
                        print(f"   [Flow Modification: Requested]")
                        if 'modification_instruction' in result.metadata:
                            # Show first 100 chars of instruction
                            instruction = result.metadata['modification_instruction'][:100]
                            print(f"   [Instruction: {instruction}...]")
                        if 'modification_type' in result.metadata:
                            print(f"   [Type: {result.metadata['modification_type']}]")
            
            if hasattr(result, 'confidence') and result.confidence < 1.0:
                print(f"   [Confidence: {result.confidence:.2f}]")
            if hasattr(result, 'reasoning') and result.reasoning:
                print(f"   [Reasoning: {result.reasoning}]")
            
            # Update context
            context = result.ctx if hasattr(result, 'ctx') else context
            
            # Show current state
            print("\n" + "="*60)
            print("📊 CURRENT STATE:")
            print(f"   Node: {context.current_node_id}")
            print(f"   Answers collected: {len(context.answers)}")
            for key, value in context.answers.items():
                print(f"     • {key}: {value}")
            if context.pending_field:
                print(f"   Pending field: {context.pending_field}")
            print("="*60 + "\n")
            
            # Check for completion
            if result.terminal:
                cli_adapter.print_status("🎉 Flow completed!")
                if context.answers:
                    print("\n📋 Final answers:")
                    for key, value in context.answers.items():
                        print(f"  {key}: {value}")
                break
            
            # Check for escalation
            if result.escalate:
                cli_adapter.print_status("🚨 Escalated to human agent")
                break
                
        except KeyboardInterrupt:
            cli_adapter.print_status("Interrupted by user")
            break
        except Exception as e:
            cli_adapter.print_error(f"Error processing turn: {e}")
            # Continue the conversation instead of breaking
            continue

    cli_adapter.print_status("Session ended")


if __name__ == "__main__":
    run_cli()