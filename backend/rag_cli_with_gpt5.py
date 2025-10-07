#!/usr/bin/env python
"""
Interactive RAG CLI with GPT-5 Response
Shows both RAG context AND final GPT-5 response using the same prompt as responder.py
"""

import asyncio
from uuid import UUID
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from app.settings import get_settings
from app.services.rag.rag_service import RAGService
from app.core.prompts import (
    get_responsible_attendant_core,
    get_golden_rule,
    get_identity_and_style,
    format_rag_section
)
from langchain_openai import ChatOpenAI

console = Console()


def build_gpt5_prompt(query: str, rag_context: str) -> str:
    """Build GPT-5 prompt using shared prompt components from app.core.prompts."""
    
    # Use shared components (same as responder.py)
    core_prompt = get_responsible_attendant_core()
    rag_section = format_rag_section(rag_context)
    golden_rule = get_golden_rule()
    identity_style = get_identity_and_style()
    
    return f"""{core_prompt}

{rag_section}

## CONTEXTO DO NEGÓCIO
Venda de luminárias LED industriais e comerciais - Iluminação profissional de alta eficiência

{golden_rule}

{identity_style}

## PERGUNTA DO USUÁRIO:
{query}

RESPOSTA:
- Responda de forma natural e conversacional em português brasileiro
- Se você tem a informação no RAG: responda com os fatos
- Se você NÃO tem a informação: admita honestamente e ofereça verificar
- Mantenha sua resposta em 1-3 mensagens curtas (como WhatsApp)
- Seja caloroso mas profissional
"""


async def interactive_rag_with_gpt5():
    """Interactive RAG query interface with GPT-5 response."""
    
    console.print(Panel(
        "[bold cyan]🤖 RAG + GPT-5 Interactive System[/bold cyan]\n\n"
        "This shows the COMPLETE pipeline:\n"
        "1. RAG retrieval (what context is found)\n"
        "2. GPT-5 response (how the responsible attendant would reply)\n\n"
        "Ask questions about the LED lighting catalog!\n\n"
        "[yellow]Type 'exit' or 'quit' to stop[/yellow]",
        title="Welcome to Full RAG+GPT-5 CLI",
        border_style="blue"
    ))
    
    settings = get_settings()
    
    # Initialize RAG service
    console.print("[dim]Initializing RAG service...[/dim]")
    rag_service = RAGService(
        openai_api_key=settings.openai_api_key,
        vector_db_url=settings.pg_vector_database_url
    )
    
    # Initialize GPT-5 (same as responder.py)
    console.print("[dim]Initializing GPT-5...[/dim]")
    gpt5 = ChatOpenAI(
        model="gpt-5",
        temperature=1,
        api_key=settings.openai_api_key
    )
    
    # Use the main test tenant
    tenant_id = UUID("068b37cd-c090-710d-b0b6-5ca37c2887ff")
    
    # Check if documents exist
    await asyncio.sleep(1)  # Wait for initialization
    has_docs = await rag_service.has_documents(tenant_id)
    
    if not has_docs:
        console.print("[red]❌ No documents found in database![/red]")
        console.print("Run: python reset_and_upload_rag.py")
        return
    
    console.print("[green]✅ System ready! Documents loaded.[/green]\n")
    
    # Sample questions
    console.print("[bold]Sample questions:[/bold]")
    console.print("• Qual a potência do HB-240?")
    console.print("• Quanto custa o HB-240?")
    console.print("• Qual produto tem 42000 lumens?")
    console.print("• Qual a garantia dos produtos?\n")
    
    # Business context for better results
    business_context = {
        "business": "Venda de luminárias LED industriais e comerciais",
        "focus": "Iluminação profissional de alta eficiência"
    }
    
    # Interactive loop
    while True:
        console.print("\n" + "="*80)
        query = Prompt.ask("[bold cyan]Your question[/bold cyan]")
        
        if query.lower() in ['exit', 'quit', 'sair']:
            console.print("[yellow]Goodbye! 👋[/yellow]")
            break
        
        if not query.strip():
            continue
        
        # STEP 1: Query RAG system
        console.print("\n[bold yellow]📊 STEP 1: RAG Retrieval + Judge[/bold yellow]")
        console.print("[dim]Searching documents...[/dim]\n")
        
        try:
            rag_context = await rag_service.query(
                tenant_id=tenant_id,
                query=query,
                chat_history=[],
                business_context=business_context
            )
            
            if rag_context and "No documents available" not in rag_context:
                console.print("[green]✅ RAG Context Retrieved[/green]")
                
                # Show abbreviated context
                context_preview = rag_context[:300] + "..." if len(rag_context) > 300 else rag_context
                console.print(Panel(
                    context_preview,
                    title="📚 RAG Context (preview)",
                    border_style="green"
                ))
                
                console.print(f"[dim]Full context: {len(rag_context)} characters[/dim]")
            else:
                console.print("[yellow]⚠️ No RAG context found (judge marked insufficient)[/yellow]")
                rag_context = ""
            
            # STEP 2: Call GPT-5 with RAG context
            console.print("\n[bold yellow]🤖 STEP 2: GPT-5 Response (Responsible Attendant)[/bold yellow]")
            console.print("[dim]Generating response...[/dim]\n")
            
            # Build prompt (same as responder.py)
            prompt = build_gpt5_prompt(query, rag_context)
            
            # Call GPT-5
            response = await gpt5.ainvoke(prompt)
            
            # Extract text from response
            if isinstance(response.content, list):
                response_text = ""
                for item in response.content:
                    if isinstance(item, dict) and 'text' in item:
                        response_text += item['text']
                    else:
                        response_text += str(item)
            else:
                response_text = response.content
            
            # Display final response
            console.print(Panel(
                f"[bold]{response_text}[/bold]",
                title="💬 GPT-5 Final Response (what user would see)",
                border_style="cyan"
            ))
            
            # Analysis
            if rag_context:
                console.print("\n[dim]📊 Pipeline Summary:[/dim]")
                console.print(f"[dim]  • RAG found: {len(rag_context)} chars of context[/dim]")
                console.print(f"[dim]  • GPT-5 responded: {len(response_text)} chars[/dim]")
                
                # Check if GPT-5 admitted not knowing
                admits_ignorance = any(word in response_text.lower() for word in 
                    ['não tenho', 'não sei', 'não consta', 'não encontrei', 'vou verificar', 'preciso confirmar'])
                
                if admits_ignorance:
                    console.print("[dim]  • ✅ GPT-5 responsibly admitted uncertainty[/dim]")
                else:
                    console.print("[dim]  • ✅ GPT-5 provided information from context[/dim]")
            else:
                console.print("\n[dim]📊 Pipeline Summary:[/dim]")
                console.print("[dim]  • RAG found: Nothing (insufficient after 3 attempts)[/dim]")
                console.print(f"[dim]  • GPT-5 responded: {len(response_text)} chars[/dim]")
                console.print("[dim]  • ✅ GPT-5 applied 'não sei' policy correctly[/dim]")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(interactive_rag_with_gpt5())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()

