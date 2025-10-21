#!/usr/bin/env python
"""
RAG System CLI - Interactive testing tool for RAG queries
Usage: python rag_cli.py
"""

import asyncio
import sys
from uuid import UUID

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from app.services.rag.embedding import EmbeddingService
from app.services.rag.rag_service import RAGService
from app.services.rag.vector_store import VectorStoreRepository
from app.settings import get_settings

console = Console()

class RAGCLITester:
    def __init__(self):
        self.settings = get_settings()
        self.tenant_id = UUID("44b613e6-c5a2-4f41-bae0-05b168245ac7")  # Tenant with documents
        self.rag_service = RAGService(
            openai_api_key=self.settings.openai_api_key,
            vector_db_url=self.settings.vector_database_url
        )
        self.vector_store = VectorStoreRepository(self.settings.vector_database_url)
        self.embedding_service = EmbeddingService(self.settings.openai_api_key)
        
    async def show_documents(self):
        """Display all documents and chunks for the tenant."""
        console.print("\n[bold cyan]📚 Documents in Database:[/bold cyan]\n")
        
        documents = await self.vector_store.get_tenant_documents(self.tenant_id)
        
        if not documents:
            console.print("[yellow]No documents found for this tenant[/yellow]")
            return
            
        for doc in documents:
            # Create document info table
            table = Table(title=f"📄 {doc['file_name']}", show_header=True, header_style="bold magenta")
            table.add_column("Property", style="cyan", width=20)
            table.add_column("Value", style="white")
            
            table.add_row("Document ID", str(doc["id"]))
            table.add_row("File Type", doc["file_type"])
            table.add_row("File Size", f"{doc.get('file_size', 'N/A')} bytes" if doc.get("file_size") else "N/A")
            table.add_row("Created At", str(doc["created_at"]))
            table.add_row("Total Chunks", str(doc["chunk_count"]))
            
            console.print(table)
            
            # Show chunk preview
            if doc.get("chunks"):
                console.print("\n[bold]First 3 chunks:[/bold]")
                for i, chunk in enumerate(doc["chunks"][:3], 1):
                    preview = chunk["content"][:150] + "..." if len(chunk["content"]) > 150 else chunk["content"]
                    console.print(f"  [dim]Chunk {i}:[/dim] {preview}")
            console.print("")
    
    async def show_indexes(self):
        """Display database indexes."""
        console.print("\n[bold cyan]🗂️ Database Indexes:[/bold cyan]\n")
        
        indexes = await self.vector_store.get_indexes()
        
        table = Table(title="Vector Database Indexes", show_header=True, header_style="bold magenta")
        table.add_column("Index Name", style="cyan", width=40)
        table.add_column("Table", style="yellow", width=20)
        table.add_column("Type", style="green", width=15)
        table.add_column("Column", style="white", width=20)
        
        for idx in indexes:
            table.add_row(
                idx.get("indexname", "N/A"),
                idx.get("tablename", "N/A"),
                idx.get("index_type", "N/A"),
                idx.get("column", "N/A")
            )
        
        console.print(table)
    
    async def test_query(self, query: str, show_details: bool = False):
        """Test a single query against the RAG system."""
        console.print(f"\n[bold cyan]🔍 Query:[/bold cyan] {query}\n")
        
        # Get query embedding
        query_embedding = await self.embedding_service.embed_text(query)
        
        # Search for similar chunks
        chunks = await self.vector_store.search_similar_chunks(
            tenant_id=self.tenant_id,
            query_embedding=query_embedding,
            limit=5,
            similarity_threshold=0.3
        )
        
        if not chunks:
            console.print("[red]❌ No chunks found[/red]")
            return
            
        # Display results table
        table = Table(title="Retrieved Chunks", show_header=True, header_style="bold magenta")
        table.add_column("#", style="cyan", width=3)
        table.add_column("Score", style="yellow", width=8)
        table.add_column("Category", style="green", width=15)
        table.add_column("Content Preview", style="white", width=60)
        
        for i, chunk in enumerate(chunks, 1):
            preview = chunk.content[:100] + "..." if len(chunk.content) > 100 else chunk.content
            preview = preview.replace("\n", " ")
            table.add_row(
                str(i),
                f"{chunk.score:.3f}",
                chunk.category or "N/A",
                preview
            )
        
        console.print(table)
        
        if show_details:
            console.print("\n[bold cyan]🤖 Running full RAG pipeline with LangGraph...[/bold cyan]\n")
            
            # Run full RAG query
            result = await self.rag_service.query(
                tenant_id=self.tenant_id,
                query=query,
                chat_history=[],
                business_context={"business": "Venda de luminárias LED"}
            )
            
            console.print(Panel(
                result,
                title="RAG System Response",
                title_align="left",
                border_style="green"
            ))
    
    async def interactive_mode(self):
        """Run interactive query mode."""
        console.print(Panel(
            "[bold cyan]RAG System Interactive Tester[/bold cyan]\n\n"
            "Commands:\n"
            "  [green]query[/green] <text>  - Test a query\n"
            "  [green]full[/green] <text>   - Test with full RAG pipeline\n"
            "  [green]docs[/green]          - Show documents in DB\n"
            "  [green]indexes[/green]       - Show database indexes\n"
            "  [green]stats[/green]         - Show system statistics\n"
            "  [green]help[/green]          - Show this help\n"
            "  [green]exit[/green]          - Exit the CLI\n",
            title="Welcome",
            border_style="blue"
        ))
        
        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]RAG>[/bold cyan]")
                
                if not user_input.strip():
                    continue
                    
                parts = user_input.strip().split(None, 1)
                command = parts[0].lower()
                
                if command == "exit":
                    console.print("[yellow]Goodbye! 👋[/yellow]")
                    break
                    
                if command == "help":
                    console.print(Panel(
                        "Commands:\n"
                        "  [green]query[/green] <text>  - Test a query (similarity only)\n"
                        "  [green]full[/green] <text>   - Test with full RAG pipeline\n"
                        "  [green]docs[/green]          - Show documents in DB\n"
                        "  [green]indexes[/green]       - Show database indexes\n"
                        "  [green]stats[/green]         - Show system statistics\n"
                        "  [green]exit[/green]          - Exit the CLI\n",
                        title="Help",
                        border_style="blue"
                    ))
                    
                elif command == "docs":
                    await self.show_documents()
                    
                elif command == "indexes":
                    await self.show_indexes()
                    
                elif command == "stats":
                    has_docs = await self.rag_service.has_documents(self.tenant_id)
                    chunk_count = await self.vector_store.get_chunk_count(self.tenant_id)
                    
                    stats_table = Table(title="System Statistics", show_header=True, header_style="bold magenta")
                    stats_table.add_column("Metric", style="cyan", width=30)
                    stats_table.add_column("Value", style="yellow", width=40)
                    
                    stats_table.add_row("Tenant ID", str(self.tenant_id))
                    stats_table.add_row("Has Documents", "✅ Yes" if has_docs else "❌ No")
                    stats_table.add_row("Total Chunks", str(chunk_count))
                    stats_table.add_row("Embedding Model", "text-embedding-3-large")
                    stats_table.add_row("Embedding Dimensions", "2000")
                    stats_table.add_row("Chunking Model", "GPT-5 (high reasoning)")
                    stats_table.add_row("Judge Model", "GPT-5-mini")
                    stats_table.add_row("Vector DB", "pgvector with ivfflat")
                    
                    console.print("\n")
                    console.print(stats_table)
                    
                elif command == "query":
                    if len(parts) < 2:
                        console.print("[red]Please provide a query text[/red]")
                    else:
                        await self.test_query(parts[1], show_details=False)
                        
                elif command == "full":
                    if len(parts) < 2:
                        console.print("[red]Please provide a query text[/red]")
                    else:
                        await self.test_query(parts[1], show_details=True)
                        
                else:
                    # Treat as a query if no command recognized
                    await self.test_query(user_input, show_details=False)
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]Use 'exit' to quit[/yellow]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

async def main():
    """Main entry point."""
    tester = RAGCLITester()
    
    # Check if we have command line arguments
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        await tester.test_query(query, show_details=True)
    else:
        # Interactive mode
        await tester.interactive_mode()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nGoodbye! 👋")
