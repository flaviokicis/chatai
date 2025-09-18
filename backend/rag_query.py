#!/usr/bin/env python
"""
Simple RAG Query Tester
Usage: python rag_query.py "your query here"
"""

import asyncio
import sys
from uuid import UUID
from app.settings import get_settings
from app.services.rag.rag_service import RAGService

async def test_rag_query(query: str):
    """Test a RAG query and show results."""
    
    settings = get_settings()
    tenant_id = UUID("44b613e6-c5a2-4f41-bae0-05b168245ac7")
    
    print(f"\n{'='*80}")
    print(f"🔍 TESTING RAG QUERY")
    print(f"{'='*80}")
    print(f"Query: {query}\n")
    
    # Initialize RAG service
    rag_service = RAGService(
        openai_api_key=settings.openai_api_key,
        vector_db_url=settings.vector_database_url
    )
    
    # Check if tenant has documents
    has_docs = await rag_service.has_documents(tenant_id)
    if not has_docs:
        print("❌ No documents found for tenant")
        return
        
    print("✅ Documents found, querying...\n")
    
    # Run RAG query with business context
    business_context = {
        "business": "Venda de luminárias LED industriais e comerciais",
        "products": ["HB-240", "CP-200", "UFO 300W", "CANOPY LED"],
        "focus": "Iluminação profissional de alta eficiência"
    }
    
    try:
        result = await rag_service.query(
            tenant_id=tenant_id,
            query=query,
            chat_history=[],
            business_context=business_context
        )
        
        print("-" * 80)
        print("📝 RAG SYSTEM RESPONSE:")
        print("-" * 80)
        print(result)
        print("-" * 80)
        
        # Show if it found content or needs escalation
        if "Nothing relevant was found" in result:
            print("\n⚠️ Status: No relevant information found - would escalate to human")
        else:
            print("\n✅ Status: Found relevant context for the query")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python rag_query.py \"your query here\"")
        print("\nExample queries:")
        print('  python rag_query.py "Qual a potência do CP-200?"')
        print('  python rag_query.py "luminária para posto de gasolina"')
        print('  python rag_query.py "garantia 5 anos"')
        print('  python rag_query.py "produto com IP66"')
        print('  python rag_query.py "quantos lumens tem o HB-240?"')
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    asyncio.run(test_rag_query(query))
