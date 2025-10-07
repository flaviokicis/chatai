#!/usr/bin/env python
"""
Direct test script for admin command system.

Tests both communication style and flow modification executors directly.
"""

import asyncio
from uuid import UUID

from rich.console import Console

from app.db.session import create_session
from app.db.repository import get_tenant_by_id
from app.services.admin_phone_service import AdminPhoneService
from app.flow_core.actions.communication_style import CommunicationStyleExecutor
from app.core.llm import create_llm_client

console = Console()


async def test_communication_style_update(
    tenant_id: UUID, admin_phone: str, instruction: str
):
    """Test communication style update directly."""
    console.print(f"\n[bold cyan]Testing Communication Style Update[/bold cyan]")
    console.print(f"Tenant: {tenant_id}")
    console.print(f"Admin: {admin_phone}")
    console.print(f"Instruction: [yellow]{instruction}[/yellow]\n")

    # Show current style
    with create_session() as session:
        tenant = get_tenant_by_id(session, tenant_id)
        if tenant and tenant.project_config:
            current_style = tenant.project_config.communication_style or "(empty)"
            console.print(f"[dim]Current style:[/dim]\n{current_style}\n")

    # Execute style update
    executor = CommunicationStyleExecutor()
    
    parameters = {"communication_style_instruction": instruction}
    context = {
        "user_id": f"whatsapp:{admin_phone}",
        "tenant_id": tenant_id,
    }

    result = await executor.execute(parameters, context)

    # Show result
    if result.success:
        console.print(f"[green]✅ Success:[/green] {result.message}")
        if result.details:
            console.print(f"[dim]Details: {result.details}[/dim]")
    else:
        console.print(f"[red]❌ Failed:[/red] {result.message}")
        if result.details:
            console.print(f"[dim]Details: {result.details}[/dim]")

    # Show updated style
    with create_session() as session:
        tenant = get_tenant_by_id(session, tenant_id)
        if tenant and tenant.project_config:
            updated_style = tenant.project_config.communication_style or "(empty)"
            console.print(f"\n[bold green]Updated style:[/bold green]\n{updated_style}\n")


async def test_admin_status(tenant_id: UUID, phone_number: str):
    """Test admin status checking."""
    console.print(f"\n[bold cyan]Testing Admin Status[/bold cyan]")
    console.print(f"Tenant: {tenant_id}")
    console.print(f"Phone: {phone_number}\n")

    with create_session() as session:
        admin_service = AdminPhoneService(session)
        
        # Check if admin
        is_admin = admin_service.is_admin_phone(phone_number, tenant_id)
        console.print(f"Is admin: [{'green' if is_admin else 'red'}]{is_admin}[/]")
        
        # List all admin phones
        admin_phones = admin_service.list_admin_phones(tenant_id)
        console.print(f"Admin phones for tenant: {admin_phones}")


async def main():
    """Run tests."""
    import argparse

    parser = argparse.ArgumentParser(description="Test admin command system directly")
    parser.add_argument("--tenant-id", type=UUID, required=True, help="Tenant ID")
    parser.add_argument(
        "--admin-phone", required=True, help="Admin phone (e.g., +5511999999999)"
    )
    parser.add_argument(
        "--instruction",
        default="Use menos emojis. Evite excesso de emojis nas mensagens. Seja mais direto e profissional.",
        help="Communication style instruction to test",
    )
    parser.add_argument(
        "--add-admin", action="store_true", help="Add phone as admin first"
    )
    args = parser.parse_args()

    # Add as admin if requested
    if args.add_admin:
        with create_session() as session:
            admin_service = AdminPhoneService(session)
            admin_service.add_admin_phone(args.admin_phone, args.tenant_id)
            session.commit()
        console.print(f"[green]✅ Added {args.admin_phone} as admin[/green]")

    # Test admin status
    await test_admin_status(args.tenant_id, args.admin_phone)

    # Test communication style update
    await test_communication_style_update(
        args.tenant_id, args.admin_phone, args.instruction
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

