#!/usr/bin/env python
"""
Test Flow Modification System Directly

This tests the actual flow modification executor (modify_flow action),
NOT communication style changes.

Tests whether FlowModificationExecutor → FlowChatService → FlowChatAgent
is working properly.
"""

import asyncio
from uuid import UUID

from rich.console import Console
from rich.panel import Panel

from app.db.session import create_session
from app.db.models import Flow
from app.services.admin_phone_service import AdminPhoneService
from app.flow_core.actions.flow_modification import FlowModificationExecutor
from app.core.llm import create_llm_client

console = Console()


async def test_flow_modification(
    flow_id: UUID, tenant_id: UUID, admin_phone: str, instruction: str
):
    """Test flow modification directly via FlowModificationExecutor."""
    
    console.print(Panel(
        f"[bold cyan]Testing Flow Modification System[/bold cyan]\n\n"
        f"Flow ID: {flow_id}\n"
        f"Tenant ID: {tenant_id}\n"
        f"Admin: {admin_phone}\n\n"
        f"Instruction: [yellow]{instruction}[/yellow]",
        title="Flow Modification Test",
        border_style="blue"
    ))
    
    # Show original flow
    console.print("\n[bold]Original Flow:[/bold]")
    with create_session() as session:
        flow = session.get(Flow, flow_id)
        if not flow:
            console.print(f"[red]Flow {flow_id} not found![/red]")
            return
        
        flow_def = flow.definition
        console.print(f"Version: {flow.version}")
        console.print(f"Nodes: {len(flow_def.get('nodes', []))}")
        
        # Show first few nodes
        for i, node in enumerate(flow_def.get('nodes', [])[:3]):
            console.print(f"  Node {i+1}: {node.get('id')} - {node.get('kind')}")
            if node.get('prompt'):
                prompt_preview = node['prompt'][:100] + "..." if len(node.get('prompt', '')) > 100 else node.get('prompt', '')
                console.print(f"    Prompt: [dim]{prompt_preview}[/dim]")
    
    # Execute modification
    console.print("\n[bold cyan]Executing Modification...[/bold cyan]")
    
    llm_client = create_llm_client()
    executor = FlowModificationExecutor(llm_client)
    
    parameters = {
        "flow_modification_instruction": instruction,
        "flow_modification_target": None,  # Let it figure out which node
        "flow_modification_type": "general",
    }
    
    context = {
        "user_id": f"whatsapp:{admin_phone}",
        "tenant_id": tenant_id,
        "flow_id": flow_id,
    }
    
    result = await executor.execute(parameters, context)
    
    # Show result
    console.print("\n[bold]Modification Result:[/bold]")
    if result.success:
        console.print(f"[green]✅ Success:[/green] {result.message}")
        if result.data:
            console.print(f"[green]Summary:[/green] {result.data.get('summary', 'N/A')}")
    else:
        console.print(f"[red]❌ Failed:[/red] {result.message}")
        if result.error:
            console.print(f"[red]Error:[/red] {result.error}")
    
    # Show updated flow
    console.print("\n[bold]Updated Flow:[/bold]")
    with create_session() as session:
        flow = session.get(Flow, flow_id)
        if flow:
            flow_def = flow.definition
            console.print(f"Version: [green]{flow.version}[/green]")
            console.print(f"Nodes: [green]{len(flow_def.get('nodes', []))}[/green]")
            
            # Show first few nodes
            for i, node in enumerate(flow_def.get('nodes', [])[:3]):
                console.print(f"  Node {i+1}: {node.get('id')} - {node.get('kind')}")
                if node.get('prompt'):
                    prompt_preview = node['prompt'][:100] + "..." if len(node.get('prompt', '')) > 100 else node.get('prompt', '')
                    console.print(f"    Prompt: [dim]{prompt_preview}[/dim]")


async def test_flow_chat_service_directly(flow_id: UUID, instruction: str):
    """Test FlowChatService directly (bypassing executor)."""
    
    console.print(Panel(
        f"[bold cyan]Testing FlowChatService Directly[/bold cyan]\n\n"
        f"Flow ID: {flow_id}\n"
        f"Instruction: [yellow]{instruction}[/yellow]",
        title="FlowChatService Direct Test",
        border_style="magenta"
    ))
    
    from app.services.flow_chat_service import FlowChatService
    from app.agents.flow_chat_agent import FlowChatAgent
    
    llm = create_llm_client()
    agent = FlowChatAgent(llm=llm)
    
    with create_session() as session:
        service = FlowChatService(session, agent=agent)
        
        console.print("\n[dim]Sending message to FlowChatService...[/dim]")
        response = await service.send_user_message(flow_id, instruction)
        
        console.print("\n[bold]FlowChatService Response:[/bold]")
        console.print(f"Flow was modified: [{'green' if response.flow_was_modified else 'red'}]{response.flow_was_modified}[/]")
        console.print(f"Message: {response.message}")
        if response.modification_summary:
            console.print(f"Summary: [cyan]{response.modification_summary}[/cyan]")


async def main():
    """Run tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test flow modification system")
    parser.add_argument("--flow-id", type=UUID, required=True, help="Flow ID to modify")
    parser.add_argument("--tenant-id", type=UUID, required=True, help="Tenant ID")
    parser.add_argument(
        "--admin-phone",
        default="+5511999999999",
        help="Admin phone number",
    )
    parser.add_argument(
        "--instruction",
        default="Change the first question to ask for the user's full name instead of just first name",
        help="Modification instruction",
    )
    parser.add_argument(
        "--add-admin",
        action="store_true",
        help="Add phone as admin first",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Test FlowChatService directly (bypass executor)",
    )
    args = parser.parse_args()
    
    # Add as admin if requested
    if args.add_admin:
        with create_session() as session:
            admin_service = AdminPhoneService(session)
            admin_service.add_admin_phone(args.admin_phone, args.tenant_id)
            session.commit()
        console.print(f"[green]✅ Added {args.admin_phone} as admin[/green]\n")
    
    if args.direct:
        # Test FlowChatService directly
        await test_flow_chat_service_directly(args.flow_id, args.instruction)
    else:
        # Test full flow modification executor
        await test_flow_modification(
            args.flow_id,
            args.tenant_id,
            args.admin_phone,
            args.instruction,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()

