#!/usr/bin/env python
"""
Complete RAG Integration Test Script
Tests the full RAG system with document upload and querying

Usage: 
    python test_rag_integration.py --upload    # Upload documents first
    python test_rag_integration.py --query     # Run test queries
    python test_rag_integration.py --flow      # Test through flow runner
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
import argparse

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.settings import get_settings
from app.services.rag.rag_service import RAGService
from app.flow_core.runner import FlowTurnRunner
from app.flow_core.state import FlowContext
from app.flow_core.compiler import FlowCompiler
from app.flow_core.ir import Flow
from app.core.llm import LLMClient
from app.core.langchain_adapter import LangChainToolsLLM
from langchain.chat_models import init_chat_model

# Rich for beautiful output
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class RAGIntegrationTester:
    """Complete RAG integration testing tool."""
    
    def __init__(self):
        self.settings = get_settings()
        self.tenant_id = None
        self.rag_service = None
        self.documents_dir = Path("playground/documents/pdfs")
        
    async def setup(self):
        """Initialize services and database."""
        console.print("[bold cyan]🔧 Setting up test environment...[/bold cyan]")
        
        # Initialize RAG service
        pg_vector_url = self.settings.pg_vector_database_url
        if not pg_vector_url:
            console.print("[red]❌ PG_VECTOR_DATABASE_URL not configured![/red]")
            console.print("[yellow]Set it in your .env file:[/yellow]")
            console.print("PG_VECTOR_DATABASE_URL=postgresql://user:pass@localhost:5432/chatai_vectors")
            return False
            
        self.rag_service = RAGService(
            openai_api_key=self.settings.openai_api_key,
            vector_db_url=pg_vector_url,
            max_retrieval_attempts=3
        )
        
        # Wait for RAG service initialization
        await asyncio.sleep(1)
        
        # Create or get test tenant
        await self.setup_tenant()
        
        console.print("[green]✅ Setup complete![/green]")
        return True
        
    async def setup_tenant(self):
        """Use the main test tenant."""
        # Use the main test tenant ID
        self.tenant_id = UUID("068b37cd-c090-710d-b0b6-5ca37c2887ff")
        console.print(f"[cyan]Using test tenant: {self.tenant_id}[/cyan]")
            
    async def upload_documents(self):
        """Upload all documents from playground/documents."""
        if not self.tenant_id or not self.rag_service:
            console.print("[red]❌ Setup required first![/red]")
            return
            
        console.print("\n[bold cyan]📤 Uploading Documents[/bold cyan]\n")
        
        # Check if tenant already has documents
        has_docs = await self.rag_service.has_documents(self.tenant_id)
        if has_docs:
            console.print("[yellow]⚠️ Tenant already has documents. Clearing first...[/yellow]")
            await self.rag_service.vector_store.clear_tenant_documents(self.tenant_id)
            console.print("[green]✅ Cleared existing documents[/green]\n")
        
        # Get all PDF files
        pdf_files = list(self.documents_dir.glob("*.pdf"))
        
        if not pdf_files:
            console.print(f"[red]No PDF files found in {self.documents_dir}[/red]")
            return
            
        console.print(f"Found {len(pdf_files)} PDF files to upload:\n")
        
        # Create results table
        results_table = Table(show_header=True, header_style="bold magenta")
        results_table.add_column("File", style="cyan", width=30)
        results_table.add_column("Status", style="green", width=10)
        results_table.add_column("Chunks", style="yellow", width=10)
        results_table.add_column("Words", style="blue", width=10)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            for pdf_file in pdf_files:
                task_id = progress.add_task(f"Processing {pdf_file.name}...", total=1)
                
                try:
                    # Upload document
                    metadata = {
                        "original_filename": pdf_file.name,
                        "tenant_id": str(self.tenant_id),
                        "business_name": "RAG Test Company",
                        "upload_source": "test_script"
                    }
                    
                    result = await self.rag_service.save_document(
                        tenant_id=self.tenant_id,
                        file_path=str(pdf_file),
                        metadata=metadata
                    )
                    
                    if result.get('success'):
                        results_table.add_row(
                            pdf_file.name,
                            "✅ Success",
                            str(result.get('chunks_created', 0)),
                            str(result.get('total_words', 0))
                        )
                    else:
                        results_table.add_row(
                            pdf_file.name,
                            "❌ Failed",
                            "-",
                            "-"
                        )
                        console.print(f"[red]Error: {result.get('error')}[/red]")
                        
                except Exception as e:
                    results_table.add_row(
                        pdf_file.name,
                        "❌ Error",
                        "-",
                        "-"
                    )
                    console.print(f"[red]Error uploading {pdf_file.name}: {e}[/red]")
                    
                progress.update(task_id, completed=1)
        
        console.print("\n")
        console.print(results_table)
        
        # Show final stats
        chunk_count = await self.rag_service.vector_store.get_tenant_chunks_count(self.tenant_id)
        console.print(f"\n[bold green]✅ Upload complete! Total chunks in database: {chunk_count}[/bold green]")
        
    async def test_queries(self):
        """Test various queries against the RAG system."""
        if not self.tenant_id or not self.rag_service:
            console.print("[red]❌ Setup required first![/red]")
            return
            
        # Check if tenant has documents
        has_docs = await self.rag_service.has_documents(self.tenant_id)
        if not has_docs:
            console.print("[red]❌ No documents found! Run with --upload first.[/red]")
            return
            
        console.print("\n[bold cyan]🔍 Testing RAG Queries[/bold cyan]\n")
        
        # Test queries - Portuguese since documents are in Portuguese
        test_queries = [
            "Qual a potência da luminária HB-240?",
            "Quantos lumens tem o CP-200?",
            "Qual produto é recomendado para posto de gasolina?",
            "Produtos com proteção IP66",
            "Qual a garantia das luminárias?",
            "Como instalar a luminária UFO?",
            "Diferença entre HB-240 e CP-200",
            "Iluminação para ginásio esportivo",
            "Produtos com 150 lumens por watt"
        ]
        
        # Business context
        business_context = {
            "business": "Venda de luminárias LED industriais e comerciais",
            "products": ["HB-240", "CP-200", "UFO 300W", "CANOPY LED"],
            "focus": "Iluminação profissional de alta eficiência"
        }
        
        for i, query in enumerate(test_queries, 1):
            console.print(f"\n[bold]Query {i}:[/bold] {query}")
            console.print("-" * 60)
            
            try:
                # Run RAG query
                result = await self.rag_service.query(
                    tenant_id=self.tenant_id,
                    query=query,
                    chat_history=[],
                    business_context=business_context
                )
                
                # Display result in a nice panel
                if result and "No documents available" not in result:
                    # Truncate if too long
                    display_result = result[:500] + "..." if len(result) > 500 else result
                    console.print(Panel(
                        display_result,
                        title="RAG Response",
                        title_align="left",
                        border_style="green"
                    ))
                else:
                    console.print("[yellow]⚠️ No relevant documents found[/yellow]")
                    
            except Exception as e:
                console.print(f"[red]❌ Error: {e}[/red]")
                
    async def test_flow_integration(self):
        """Test RAG through the FlowTurnRunner."""
        if not self.tenant_id or not self.rag_service:
            console.print("[red]❌ Setup required first![/red]")
            return
            
        console.print("\n[bold cyan]🔄 Testing Flow Integration[/bold cyan]\n")
        
        # Initialize LLM
        chat = init_chat_model(
            self.settings.llm_model,
            model_provider=self.settings.llm_provider
        )
        llm_client = LangChainToolsLLM(chat)
        
        # Create a simple test flow
        test_flow = {
            "id": "test-flow",
            "name": "RAG Test Flow",
            "description": "Flow for testing RAG integration",
            "entry": "start",
            "nodes": [
                {
                    "id": "start",
                    "type": "question",
                    "text": "Como posso ajudar você hoje?",
                    "data_key": "user_question"
                }
            ],
            "edges": []
        }
        
        # Compile flow
        flow_obj = Flow.model_validate(test_flow)
        compiler = FlowCompiler()
        compiled_flow = compiler.compile(flow_obj)
        
        # Create runner WITH RAG service
        runner = FlowTurnRunner(
            llm_client=llm_client,
            compiled_flow=compiled_flow,
            rag_service=self.rag_service  # Pass RAG service!
        )
        
        # Initialize context
        ctx = FlowContext(
            flow_id="test-flow",
            user_id="test-user",
            session_id=str(uuid4()),
            tenant_id=self.tenant_id,  # Important: set tenant_id!
            channel_id="test-channel",
            current_node_id="start"
        )
        
        # Test queries through the flow
        test_messages = [
            "Qual a potência da luminária HB-240?",
            "Preciso de iluminação para um posto de gasolina",
            "Quanto custa o modelo CP-200?"
        ]
        
        for msg in test_messages:
            console.print(f"\n[bold]User:[/bold] {msg}")
            console.print("-" * 60)
            
            # Process through flow runner (will query RAG automatically!)
            result = await runner.process_turn(
                ctx=ctx,
                user_message=msg,
                project_context=None,
                is_admin=False
            )
            
            # Check if RAG was used
            if ctx.rag_query_performed:
                console.print("[green]✅ RAG query performed![/green]")
                if ctx.rag_documents:
                    console.print(f"[cyan]Found {len(ctx.rag_documents)} relevant documents[/cyan]")
                    # Show first document snippet
                    if ctx.rag_documents[0].get('content'):
                        snippet = ctx.rag_documents[0]['content'][:200] + "..."
                        console.print(f"[dim]Context preview: {snippet}[/dim]\n")
            else:
                console.print("[yellow]⚠️ RAG query not performed[/yellow]")
                
            # Show response
            if result.metadata.get('messages'):
                for message in result.metadata['messages']:
                    if message.get('text'):
                        console.print(Panel(
                            message['text'][:500] + "..." if len(message['text']) > 500 else message['text'],
                            title="Assistant Response",
                            border_style="blue"
                        ))
                        
    async def interactive_query(self):
        """Interactive query mode."""
        if not self.tenant_id or not self.rag_service:
            console.print("[red]❌ Setup required first![/red]")
            return
            
        console.print("\n[bold cyan]💬 Interactive RAG Query Mode[/bold cyan]")
        console.print("[dim]Type 'exit' to quit[/dim]\n")
        
        business_context = {
            "business": "Venda de luminárias LED industriais e comerciais",
            "focus": "Iluminação profissional de alta eficiência"
        }
        
        while True:
            try:
                query = input("\n[Query]> ").strip()
                
                if query.lower() == 'exit':
                    console.print("[yellow]Goodbye! 👋[/yellow]")
                    break
                    
                if not query:
                    continue
                    
                # Query RAG
                with console.status("[bold green]Searching documents...") as status:
                    result = await self.rag_service.query(
                        tenant_id=self.tenant_id,
                        query=query,
                        chat_history=[],
                        business_context=business_context
                    )
                
                # Display result
                console.print("\n" + "="*60)
                if result and "No documents available" not in result:
                    console.print(Panel(
                        result,
                        title="📚 RAG Context",
                        border_style="green"
                    ))
                else:
                    console.print("[yellow]⚠️ No relevant information found in documents[/yellow]")
                console.print("="*60)
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]Use 'exit' to quit[/yellow]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Test RAG Integration')
    parser.add_argument('--upload', action='store_true', help='Upload documents')
    parser.add_argument('--query', action='store_true', help='Test queries')
    parser.add_argument('--flow', action='store_true', help='Test flow integration')
    parser.add_argument('--interactive', action='store_true', help='Interactive query mode')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    
    args = parser.parse_args()
    
    # Default to interactive if no args
    if not any(vars(args).values()):
        args.interactive = True
    
    # Initialize tester
    tester = RAGIntegrationTester()
    
    console.print(Panel(
        "[bold cyan]RAG Integration Test Suite[/bold cyan]\n\n"
        "This tool tests the complete RAG integration:\n"
        "• Document upload from playground/documents\n"
        "• RAG queries through RAGService\n"
        "• Integration with FlowTurnRunner\n"
        "• Interactive query testing",
        title="🚀 Welcome",
        border_style="blue"
    ))
    
    # Setup
    if not await tester.setup():
        console.print("[red]Setup failed! Check configuration.[/red]")
        return
        
    # Run requested operations
    if args.all or args.upload:
        await tester.upload_documents()
        
    if args.all or args.query:
        await tester.test_queries()
        
    if args.all or args.flow:
        await tester.test_flow_integration()
        
    if args.interactive:
        await tester.interactive_query()
        

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        import traceback
        traceback.print_exc()


