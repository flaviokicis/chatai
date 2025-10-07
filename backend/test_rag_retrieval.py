#!/usr/bin/env python3
"""
Test RAG Retrieval + Judge Pipeline (without GPT-5 tool caller)

This shows exactly what the RAG system retrieves and what the judge decides,
BEFORE it gets passed to GPT-5/tool caller in responder.py

Usage: python test_rag_retrieval.py "your query here"
"""

import asyncio
import sys
from uuid import UUID

from app.settings import get_settings
from app.services.rag.rag_service import RAGService


async def test_retrieval_pipeline(query: str):
    """Test the retrieval + judge pipeline without GPT-5."""
    
    settings = get_settings()
    tenant_id = UUID("068b37cd-c090-710d-b0b6-5ca37c2887ff")
    
    print("\n" + "="*80)
    print("RAG RETRIEVAL + JUDGE PIPELINE TEST")
    print("="*80)
    print(f"\n📝 Query: {query}")
    print(f"🏢 Tenant: {tenant_id}\n")
    
    # Initialize RAG service
    print("🔧 Initializing RAG service...")
    rag_service = RAGService(
        openai_api_key=settings.openai_api_key,
        vector_db_url=settings.pg_vector_database_url,
        max_retrieval_attempts=3
    )
    
    await asyncio.sleep(1)  # Wait for initialization
    
    # Check if tenant has documents
    has_docs = await rag_service.has_documents(tenant_id)
    if not has_docs:
        print("❌ No documents found for this tenant!")
        print("Run: python reset_and_upload_rag.py")
        return
    
    print("✅ Documents found!\n")
    
    # Run the full RAG query (this includes retrieval + judge)
    print("="*80)
    print("RUNNING RAG QUERY (Retrieval → Judge)")
    print("="*80 + "\n")
    
    business_context = {
        "business": "Venda de luminárias LED industriais e comerciais",
        "focus": "Iluminação profissional de alta eficiência"
    }
    
    # This runs the full pipeline including judge
    result = await rag_service.query(
        tenant_id=tenant_id,
        query=query,
        chat_history=[],
        business_context=business_context,
        thread_id=None
    )
    
    print("\n" + "="*80)
    print("RESULT: What would be passed to GPT-5/Tool Caller")
    print("="*80 + "\n")
    
    if result:
        print("📤 Context that would go to @responder.py:\n")
        print(result)
        print("\n" + "="*80)
        print("✅ This context would be injected into GPT-5's prompt")
        print("   GPT-5 would then decide how to respond to the user")
        print("="*80)
    else:
        print("📭 Empty result (judge marked insufficient after max attempts)")
        print("   GPT-5 would see NO RAG context")
        print("   → Tool caller would apply the 'não sei' policy")
        print("="*80)
    
    print("\n💡 To see the full flow including GPT-5 response:")
    print("   python simple_rag_cli.py\n")


async def test_detailed_retrieval(query: str):
    """Show detailed retrieval steps."""
    
    settings = get_settings()
    tenant_id = UUID("068b37cd-c090-710d-b0b6-5ca37c2887ff")
    
    print("\n" + "="*80)
    print("DETAILED RAG RETRIEVAL PIPELINE")
    print("="*80)
    print(f"\n📝 Query: {query}\n")
    
    # Initialize services manually to see each step
    from app.services.rag.embedding import EmbeddingService
    from app.services.rag.vector_store import VectorStoreRepository
    from app.services.rag.judge import JudgeService, ChunkContext
    
    embedding_service = EmbeddingService(settings.openai_api_key)
    vector_store = VectorStoreRepository(settings.pg_vector_database_url)
    judge_service = JudgeService(settings.openai_api_key)
    
    await asyncio.sleep(1)
    
    # Step 1: Generate query embedding
    print("📊 STEP 1: Generating query embedding...")
    query_embedding = await embedding_service.embed_text(query)
    print(f"   ✓ Generated {len(query_embedding)}-dimensional embedding")
    print(f"   Sample: [{query_embedding[0]:.4f}, {query_embedding[1]:.4f}, ...]")
    
    # Step 2: Vector similarity search
    print("\n🔍 STEP 2: Searching for similar chunks...")
    chunks = await vector_store.search_similar_chunks(
        tenant_id=tenant_id,
        query_embedding=query_embedding,
        limit=6,
        similarity_threshold=0.5
    )
    
    print(f"   ✓ Found {len(chunks)} chunks above threshold 0.5\n")
    
    if not chunks:
        print("   ❌ No chunks found!")
        return
    
    # Show retrieved chunks
    print("📄 RETRIEVED CHUNKS:\n")
    for i, chunk in enumerate(chunks, 1):
        print(f"   Chunk {i}:")
        print(f"   - Document: {chunk.document_name}")
        print(f"   - Similarity: {chunk.score:.3f}")
        print(f"   - Category: {chunk.category or 'General'}")
        preview = chunk.content[:150] + "..." if len(chunk.content) > 150 else chunk.content
        print(f"   - Content: {preview}")
        print()
    
    # Step 3: Judge evaluation
    print("⚖️  STEP 3: Judge evaluation...")
    
    chunk_contexts = [
        ChunkContext(
            chunk_id=str(chunk.chunk_id),
            content=chunk.content,
            score=chunk.score,
            category=chunk.category,
            possible_questions=chunk.possible_questions
        )
        for chunk in chunks
    ]
    
    judgment = await judge_service.judge_chunks(
        query=query,
        chunks=chunk_contexts,
        chat_history=[],
        business_context={
            "business": "Venda de luminárias LED",
            "focus": "Iluminação profissional"
        }
    )
    
    print(f"   Decision: {'✅ EXHAUSTED (stop retrieval)' if judgment.sufficient else '❌ CONTINUE (fetch more)'}")
    print(f"   Confidence: {judgment.confidence:.2f}")
    print(f"   Reasoning: {judgment.reasoning}")
    
    if judgment.missing_info:
        print(f"   Missing info: {', '.join(judgment.missing_info)}")
    
    print("\n" + "="*80)
    print("📤 WHAT HAPPENS NEXT:")
    print("="*80)
    
    if judgment.sufficient:
        print("✅ Judge says: 'Retrieval exhausted, this is all I can get'")
        print("   → Context is formatted and sent to GPT-5")
        print("   → GPT-5 in @responder.py decides if it can answer responsibly")
        print("   → If GPT-5 can't answer: applies 'não sei' policy")
    else:
        print("🔄 Judge says: 'Can fetch more relevant chunks'")
        print("   → RAG would try again with broader search")
        print("   → Max 3 attempts, then give up")
    
    print("="*80 + "\n")
    
    await vector_store.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\nUsage: python test_rag_retrieval.py \"your query here\"")
        print("\nExample queries:")
        print('  python test_rag_retrieval.py "Qual a potência do HB-240?"')
        print('  python test_rag_retrieval.py "Poste solar"')
        print('  python test_rag_retrieval.py "Preço do CP-200"')
        print()
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    
    try:
        print("\n🔬 MODE 1: Full Pipeline (Retrieval + Judge)")
        asyncio.run(test_retrieval_pipeline(query))
        
        print("\n" + "="*80)
        input("\nPress Enter to see detailed step-by-step breakdown...")
        
        print("\n🔬 MODE 2: Detailed Step-by-Step")
        asyncio.run(test_detailed_retrieval(query))
        
    except KeyboardInterrupt:
        print("\n\n❌ Interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

