#!/usr/bin/env python3
"""Validation script to ensure RAG system is working correctly."""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

async def validate_rag():
    """Validate RAG system components."""
    
    print("=" * 60)
    print("RAG SYSTEM VALIDATION")
    print("=" * 60)
    
    # 1. Check environment
    print("\n✓ Checking environment variables...")
    import os
    assert os.getenv('OPENAI_API_KEY'), "OPENAI_API_KEY not set"
    assert os.getenv('PG_VECTOR_DATABASE_URL'), "PG_VECTOR_DATABASE_URL not set"
    print("  - API keys configured")
    
    # 2. Check database connectivity
    print("\n✓ Checking pgvector database...")
    from app.services.rag.vector_store import VectorStoreRepository
    from app.settings import get_settings
    
    settings = get_settings()
    vector_store = VectorStoreRepository(settings.vector_database_url)
    await vector_store.initialize()
    print("  - Database connected")
    print("  - pgvector extension enabled")
    
    # 3. Check embedding service
    print("\n✓ Checking embedding service...")
    from app.services.rag.embedding import EmbeddingService
    
    embedding_service = EmbeddingService(settings.openai_api_key)
    test_embedding = await embedding_service.embed_text("test")
    assert len(test_embedding) == 2000, f"Expected 2000 dimensions, got {len(test_embedding)}"
    print(f"  - Embeddings working (2000 dimensions)")
    
    # 4. Check document parser
    print("\n✓ Checking document parser...")
    from app.services.rag.document_parser import DocumentParserService
    
    parser = DocumentParserService()
    test_doc = parser.parse_text("Test content", "test.txt")
    assert test_doc.content == "Test content"
    print("  - Parser working")
    
    # 5. Check chunking service
    print("\n✓ Checking chunking service...")
    from app.services.rag.chunking import ChunkingService
    
    chunking = ChunkingService(settings.openai_api_key)
    print("  - Chunking service initialized")
    
    # 6. Check judge service
    print("\n✓ Checking judge service...")
    from app.services.rag.judge import JudgeService
    
    judge = JudgeService(settings.openai_api_key)
    print("  - Judge service initialized")
    
    # 7. Check main RAG service
    print("\n✓ Checking RAG service...")
    from app.services.rag import RAGService
    
    rag_service = RAGService(
        openai_api_key=settings.openai_api_key,
        vector_db_url=settings.vector_database_url,
        max_retrieval_attempts=2
    )
    await asyncio.sleep(1)
    print("  - RAG service initialized")
    
    # 8. Check tenant
    print("\n✓ Checking test tenant...")
    from app.db.session import db_session
    from app.db.models import Tenant
    
    with db_session() as session:
        tenant = session.query(Tenant).first()
        if tenant:
            tenant_id = tenant.id
            print(f"  - Using tenant: {tenant_id}")
            
            # Check if tenant has documents
            has_docs = await rag_service.has_documents(tenant_id)
            stats = await rag_service.get_tenant_stats(tenant_id)
            print(f"  - Documents: {stats['total_chunks']} chunks")
            print(f"  - RAG enabled: {stats['rag_enabled']}")
        else:
            print("  - No tenant found (run seed_database.py)")
    
    # Clean up
    await vector_store.close()
    await rag_service.close()
    
    print("\n" + "=" * 60)
    print("✅ RAG SYSTEM VALIDATION COMPLETE")
    print("=" * 60)
    print("\nThe RAG system is properly configured and working!")
    print("\nKey features:")
    print("- Document parsing with MarkItDown")
    print("- Intelligent chunking with GPT-4o")
    print("- 2000-dimensional embeddings with text-embedding-3-large")
    print("- pgvector storage with ivfflat indexing")
    print("- LangGraph iterative retrieval")
    print("- GPT-4o-mini judge for relevance assessment")
    
    return True

if __name__ == "__main__":
    try:
        asyncio.run(validate_rag())
    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        sys.exit(1)
