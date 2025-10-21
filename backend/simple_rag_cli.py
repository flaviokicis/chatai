#!/usr/bin/env python
"""
Simple Interactive RAG CLI - Make free queries to test the RAG system.
Usage: python simple_rag_cli.py
"""

import asyncio
from uuid import UUID

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from app.services.rag.rag_service import RAGService
from app.settings import get_settings

console = Console()

async def interactive_rag():
    """Simple interactive RAG query interface."""
    
    console.print(Panel(
        "[bold cyan]🤖 RAG Interactive Query System[/bold cyan]\n\n"
        "Ask questions about the LED lighting catalog!\n"
        "The system will search through:\n"
        "• Product specifications\n"
        "• Technical details\n"
        "• Pricing and warranty info\n\n"
        "[yellow]Type 'exit' or 'quit' to stop[/yellow]",
        title="Welcome to RAG CLI",
        border_style="blue"
    ))
    
    settings = get_settings()
    
    # Initialize RAG service
    console.print("[dim]Initializing RAG service...[/dim]")
    rag_service = RAGService(
        openai_api_key=settings.openai_api_key,
        vector_db_url=settings.vector_database_url
    )
    
    # Use the main test tenant
    tenant_id = UUID("068b37cd-c090-710d-b0b6-5ca37c2887ff")
    
    # Check if documents exist
    await asyncio.sleep(1)  # Wait for initialization
    has_docs = await rag_service.has_documents(tenant_id)
    
    if not has_docs:
        console.print("[red]❌ No documents found in database![/red]")
        console.print("Run: python test_rag_integration.py --upload")
        return
    
    console.print("[green]✅ RAG system ready! Documents loaded.[/green]\n")
    
    # Sample questions to inspire users
    console.print("[bold]Sample questions you can ask:[/bold]")
    console.print("• Qual produto tem 42000 lumens?")
    console.print("• Luminária para posto de gasolina")
    console.print("• Qual a garantia dos produtos?")
    console.print("• Produtos com proteção IP66")
    console.print("• Quantos lumens tem o HB-200?\n")
    
    # Business context for better results
    business_context = {
        "business": "Venda de luminárias LED industriais e comerciais",
        "products": ["HB-240", "CP-200", "UFO 300W", "CANOPY LED"],
        "focus": "Iluminação profissional de alta eficiência"
    }
    
    # Interactive loop
    while True:
        console.print("\n" + "="*60)
        query = Prompt.ask("[bold cyan]Your question[/bold cyan]")
        
        if query.lower() in ["exit", "quit", "sair"]:
            console.print("[yellow]Goodbye! 👋[/yellow]")
            break
        
        if not query.strip():
            continue
        
        # Query RAG system
        console.print("[dim]Searching documents...[/dim]")
        
        try:
            result = await rag_service.query(
                tenant_id=tenant_id,
                query=query,
                chat_history=[],
                business_context=business_context
            )
            
            if result and "No documents available" not in result:
                console.print("\n[bold green]📚 RAG Context Found:[/bold green]\n")
                
                # Parse and display nicely
                lines = result.split("\n")
                for line in lines:
                    if line.startswith("##"):
                        console.print(f"[bold cyan]{line}[/bold cyan]")
                    elif line.startswith("**"):
                        console.print(f"[yellow]{line}[/yellow]")
                    elif "**Relevância:**" in line:
                        console.print(f"[green]{line}[/green]")
                    else:
                        console.print(line)
            else:
                console.print("[yellow]⚠️ No relevant information found for this query.[/yellow]")
                console.print("[dim]Try asking about products, specifications, or pricing.[/dim]")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

if __name__ == "__main__":
    try:
        asyncio.run(interactive_rag())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")

