#!/usr/bin/env python
"""
Admin Flow Testing CLI - Test admin commands for flow and communication style modification.

This CLI allows you to test the admin flow modification system interactively:
- Test flow modification commands ("Change this question to...")
- Test communication style changes ("Ta muito emoji, da uma maneirada")
- See how the system detects and handles admin commands
- Verify that modifications persist

Usage: python admin_flow_cli.py [--flow-file PATH] [--tenant-id UUID]
"""

import asyncio
import json
from pathlib import Path
from uuid import UUID

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from app.core.llm import create_llm_client
from app.db.models import ChannelType
from app.db.repository import (
    create_channel_instance,
    create_flow,
    create_tenant_with_config,
    get_tenant_by_id,
)
from app.db.session import create_session
from app.flow_core.services.responder import EnhancedFlowResponder
from app.flow_core.state import FlowContext
from app.services.admin_phone_service import AdminPhoneService
from app.services.tenant_config_service import ProjectContext
from app.settings import get_settings

console = Console()


class AdminFlowTester:
    """Interactive tester for admin flow commands."""

    def __init__(self, tenant_id: UUID, flow_id: UUID, admin_phone: str):
        self.tenant_id = tenant_id
        self.flow_id = flow_id
        self.admin_phone = admin_phone
        self.settings = get_settings()
        self.conversation_history: list[dict] = []
        self.llm_client = create_llm_client()
        # Use the actual responder that's used in production
        self.responder = EnhancedFlowResponder(self.llm_client)
        # Track flow context across messages
        self.flow_context: FlowContext | None = None

    async def send_message(self, message: str, is_admin: bool = True) -> dict:
        """Send a message directly to the EnhancedFlowResponder (production code path)."""
        user_id = f"whatsapp:{self.admin_phone}" if is_admin else "whatsapp:+19995551234"

        # Load flow definition and tenant config
        with create_session() as session:
            from app.db.models import Flow
            flow = session.get(Flow, self.flow_id)
            if not flow:
                raise ValueError(f"Flow {self.flow_id} not found")
            flow_def = flow.definition
            tenant = get_tenant_by_id(session, self.tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {self.tenant_id} not found")

        # Build project context
        project_context = ProjectContext(
            tenant_id=self.tenant_id,
            project_description=tenant.project_config.project_description if tenant.project_config else "",
            target_audience=tenant.project_config.target_audience if tenant.project_config else "",
            communication_style=tenant.project_config.communication_style if tenant.project_config else "",
        )

        # Initialize or update flow context
        if self.flow_context is None:
            # First message - initialize context at entry node
            entry_node = None
            for node in flow_def.get("nodes", []):
                if node.get("type") == "EntryNode":
                    entry_node = node
                    break
            
            if not entry_node:
                raise ValueError("No entry node found in flow")

            self.flow_context = FlowContext(
                user_id=user_id,
                tenant_id=self.tenant_id,
                session_id=f"admin-test:{user_id}",
                current_node_id=entry_node["id"],
            )

        # Get current node info
        current_node = None
        for node in flow_def.get("nodes", []):
            if node["id"] == self.flow_context.current_node_id:
                current_node = node
                break

        if not current_node:
            raise ValueError(f"Current node {self.flow_context.current_node_id} not found")

        # Get prompt from current node
        prompt = current_node.get("prompt", "")
        pending_field = current_node.get("key")
        
        # Get available edges from current node
        available_edges = []
        for edge in flow_def.get("edges", []):
            if edge.get("from") == self.flow_context.current_node_id:
                available_edges.append({
                    "target_node_id": edge["to"],
                    "label": edge.get("label", ""),
                })

        # Call the actual responder (production code!)
        responder_output = await self.responder.respond(
            prompt=prompt,
            pending_field=pending_field,
            context=self.flow_context,
            user_message=message,
            allowed_values=None,
            project_context=project_context,
            is_completion=False,
            available_edges=available_edges,
            is_admin=is_admin,
            flow_graph=flow_def,
        )

        # Update context based on tool execution results
        if responder_output.tool_result.updates:
            for key, value in responder_output.tool_result.updates.items():
                self.flow_context.answers[key] = value

        if responder_output.tool_result.navigation:
            self.flow_context.current_node_id = responder_output.tool_result.navigation

        # Format messages for display
        messages_text = "\n".join([msg["text"] for msg in responder_output.messages])

        return {
            "message": message,
            "response": messages_text,
            "tool_name": responder_output.tool_name,
            "reasoning": responder_output.reasoning,
            "confidence": responder_output.confidence,
            "metadata": responder_output.tool_result.metadata,
            "current_node": self.flow_context.current_node_id,
            "answers": dict(self.flow_context.answers),
        }

    def show_response(self, result: dict):
        """Display the bot's response in a nice format."""
        console.print("\n[bold cyan]🤖 Bot Response:[/bold cyan]")
        console.print(Panel(escape(result["response"]), border_style="cyan"))

        # Show debug info
        console.print(f"\n[dim]Tool: {result.get('tool_name', 'unknown')}[/dim]")
        console.print(f"[dim]Current Node: {result.get('current_node', 'unknown')}[/dim]")
        console.print(f"[dim]Confidence: {result.get('confidence', 0):.2f}[/dim]")
        
        if result.get("reasoning"):
            console.print(f"[dim]Reasoning: {result['reasoning']}[/dim]")

        # Show metadata if interesting
        if result.get("metadata"):
            metadata = result["metadata"]
            interesting_keys = ["action_results", "external_actions", "action_result"]
            has_interesting = any(key in metadata for key in interesting_keys)
            
            if has_interesting:
                console.print("\n[yellow]📋 Actions taken:[/yellow]")
                for key, value in metadata.items():
                    if key in interesting_keys and value:
                        console.print(f"  • {key}: {value}")
        
        # Show collected answers
        if result.get("answers"):
            console.print("\n[blue]📝 Collected data:[/blue]")
            for key, value in result["answers"].items():
                console.print(f"  • {key}: {value}")

    def show_communication_style(self):
        """Show current communication style for the tenant."""
        with create_session() as session:
            tenant = get_tenant_by_id(session, self.tenant_id)
            if tenant and tenant.project_config:
                style = tenant.project_config.communication_style or "(not set)"
                console.print("\n[bold magenta]💬 Current Communication Style:[/bold magenta]")
                console.print(Panel(escape(style), border_style="magenta"))
            else:
                console.print("[yellow]No communication style set[/yellow]")

    async def run_interactive(self):
        """Run interactive testing session."""
        console.print(Panel(
            "[bold cyan]🔧 Admin Flow Testing CLI[/bold cyan]\n\n"
            "This tool tests the ACTUAL EnhancedFlowResponder (production code).\n"
            "You're calling the same responder.respond() that runs in production!\n\n"
            "[bold]Test scenarios:[/bold]\n"
            "• Flow modifications: 'Change this question to...'\n"
            "• Communication style: 'Ta muito emoji, da uma maneirada'\n"
            "• Admin commands: Any meta-instruction about the flow\n\n"
            "[yellow]Type 'exit' to quit, 'style' to see communication style, 'reset' to restart flow[/yellow]",
            title="Admin Flow Tester (Using Real Responder)",
            border_style="blue"
        ))

        # Show admin status
        console.print(f"\n[green]✅ Admin phone:[/green] {self.admin_phone}")
        console.print(f"[green]✅ Tenant ID:[/green] {self.tenant_id}")
        console.print(f"[green]✅ Flow ID:[/green] {self.flow_id}")

        # Verify admin status
        with create_session() as session:
            admin_service = AdminPhoneService(session)
            is_admin = admin_service.is_admin_phone(self.admin_phone, self.tenant_id)
            if is_admin:
                console.print("[green]✅ Admin status: CONFIRMED[/green]")
            else:
                console.print("[red]⚠️  Admin status: NOT ADMIN[/red]")
                console.print("[yellow]Add this phone as admin first![/yellow]")

        # Show current communication style
        self.show_communication_style()

        # Sample admin commands
        console.print("\n[bold]Sample admin commands to try:[/bold]")
        console.print("• 'Ta muito emoji, da uma maneirada'")
        console.print("• 'Fale de forma mais profissional'")
        console.print("• 'Use menos emojis e seja mais direto'")
        console.print("• 'Mude a saudação para ser mais calorosa'")
        console.print("• 'Change this question to ask for full name'")
        console.print("• 'Divida esta pergunta em 2 perguntas separadas'\n")

        while True:
            console.print("\n" + "="*60)
            command = Prompt.ask("[bold cyan]Your message (as admin)[/bold cyan]")

            if command.lower() in ["exit", "quit", "sair"]:
                console.print("[yellow]Goodbye! 👋[/yellow]")
                break

            if command.lower() == "style":
                self.show_communication_style()
                continue

            if command.lower() == "reset":
                self.flow_context = None
                console.print("[yellow]Flow context reset! Starting from beginning.[/yellow]")
                continue

            if not command.strip():
                continue

            # Send message
            console.print("[dim]Calling EnhancedFlowResponder.respond()...[/dim]")

            try:
                result = await self.send_message(command, is_admin=True)
                self.show_response(result)
                self.conversation_history.append(result)

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                import traceback
                traceback.print_exc()


async def setup_test_environment(flow_file: Path | None) -> tuple[UUID, UUID, str]:
    """Set up or use existing test environment."""
    console.print("[bold]Setting up test environment...[/bold]\n")

    # Check for existing config
    config_file = Path(".admin_flow_cli_config.json")
    if config_file.exists():
        use_existing = Confirm.ask("Found existing configuration. Use it?")
        if use_existing:
            with open(config_file) as f:
                config = json.load(f)
                console.print("[green]✅ Using existing configuration[/green]")
                return (
                    UUID(config["tenant_id"]),
                    UUID(config["flow_id"]),
                    config["admin_phone"],
                )

    # Ask whether to use existing tenant or create new one
    tenant_id_input = Prompt.ask(
        "Enter existing tenant ID (or press Enter to create new)",
        default=""
    )

    with create_session() as session:
        if tenant_id_input:
            # Use existing tenant
            tenant_id = UUID(tenant_id_input)
            tenant = get_tenant_by_id(session, tenant_id)
            if not tenant:
                console.print(f"[red]Tenant {tenant_id} not found[/red]")
                return await setup_test_environment(flow_file)
            console.print(f"[green]✅ Using existing tenant: {tenant_id}[/green]")
        else:
            # Create new test tenant
            console.print("Creating new test tenant...")
            tenant = create_tenant_with_config(
                session,
                first_name="Admin",
                last_name="Test",
                email="admin-test@example.com",
                project_description="Test environment for admin flow commands",
                target_audience="Internal testing",
                communication_style="Friendly and professional",
            )
            session.commit()
            tenant_id = tenant.id
            console.print(f"[green]✅ Created tenant: {tenant_id}[/green]")

        # Set up admin phone
        admin_phone = Prompt.ask(
            "Admin phone number (for testing)",
            default="+5511999999999"
        )

        admin_service = AdminPhoneService(session)
        admin_service.add_admin_phone(admin_phone, tenant_id)
        session.commit()
        console.print(f"[green]✅ Added admin phone: {admin_phone}[/green]")

        # Create or use flow
        if flow_file and flow_file.exists():
            # Load flow from file
            console.print(f"Loading flow from {flow_file}...")
            with open(flow_file) as f:
                flow_def = json.load(f)

            # Create channel for flow
            channel = create_channel_instance(
                session,
                tenant_id=tenant_id,
                channel_type=ChannelType.whatsapp,
                identifier=f"whatsapp:+{admin_phone.replace('+', '')}",
                phone_number=admin_phone,
                extra={"display_name": "Admin Test"},
            )
            session.commit()

            # Create flow
            flow = create_flow(
                session,
                tenant_id=tenant_id,
                channel_instance_id=channel.id,
                name="Admin Test Flow",
                flow_id="flow.admin_test",
                definition=flow_def,
            )
            session.commit()
            flow_id = flow.id
            console.print(f"[green]✅ Created flow: {flow_id}[/green]")
        else:
            # Ask for existing flow ID
            flow_id_input = Prompt.ask("Enter existing flow ID")
            flow_id = UUID(flow_id_input)

            from app.db.models import Flow
            flow = session.get(Flow, flow_id)
            if not flow:
                console.print(f"[red]Flow {flow_id} not found[/red]")
                return await setup_test_environment(flow_file)
            console.print(f"[green]✅ Using existing flow: {flow_id}[/green]")

    # Save configuration
    config = {
        "tenant_id": str(tenant_id),
        "flow_id": str(flow_id),
        "admin_phone": admin_phone,
    }
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)
    console.print(f"[green]✅ Saved configuration to {config_file}[/green]\n")

    return tenant_id, flow_id, admin_phone


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test admin flow commands interactively")
    parser.add_argument("--flow-file", type=Path, help="Flow JSON file to use")
    parser.add_argument("--tenant-id", type=UUID, help="Existing tenant ID")
    parser.add_argument("--flow-id", type=UUID, help="Existing flow ID")
    parser.add_argument("--admin-phone", help="Admin phone number")
    parser.add_argument("--reset", action="store_true", help="Reset configuration")
    args = parser.parse_args()

    # Reset config if requested
    if args.reset:
        config_file = Path(".admin_flow_cli_config.json")
        if config_file.exists():
            config_file.unlink()
            console.print("[yellow]Configuration reset[/yellow]\n")

    # Set up environment
    if args.tenant_id and args.flow_id and args.admin_phone:
        tenant_id = args.tenant_id
        flow_id = args.flow_id
        admin_phone = args.admin_phone
    else:
        tenant_id, flow_id, admin_phone = await setup_test_environment(args.flow_file)

    # Run interactive tester
    tester = AdminFlowTester(tenant_id, flow_id, admin_phone)
    await tester.run_interactive()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()

