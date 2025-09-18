#!/usr/bin/env python3
"""Simple RAG system test to verify document upload and retrieval."""

import asyncio
import logging
from pathlib import Path
import sys

from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.rag import RAGService
from app.settings import get_settings
from app.db.session import db_session
from app.db.models import Tenant

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


async def test_rag_simple():
    """Simple test of RAG system."""
    
    settings = get_settings()
    
    # Get tenant ID
    with db_session() as session:
        tenant = session.query(Tenant).first()
        if not tenant:
            logger.error("No tenant found")
            return
        tenant_id = tenant.id
        logger.info(f"Using tenant: {tenant_id}")
    
    # Initialize RAG service
    rag_service = RAGService(
        openai_api_key=settings.openai_api_key,
        vector_db_url=settings.vector_database_url,
        max_retrieval_attempts=2
    )
    
    # Wait for initialization
    await asyncio.sleep(2)
    
    # Test 1: Upload a simple test document
    logger.info("\n=== TEST 1: Document Upload ===")
    
    test_file = Path("playground/documents/catalogo_de_produtos_led.md")
    if test_file.exists():
        logger.info(f"Uploading: {test_file.name}")
        result = await rag_service.save_document(
            tenant_id=tenant_id,
            file_path=str(test_file),
            metadata={"test": "simple"}
        )
        logger.info(f"Upload result: {result}")
    else:
        logger.error(f"Test file not found: {test_file}")
        return
    
    # Test 2: Check if tenant has documents
    logger.info("\n=== TEST 2: Check Documents ===")
    has_docs = await rag_service.has_documents(tenant_id)
    logger.info(f"Tenant has documents: {has_docs}")
    
    # Test 3: Get tenant stats
    logger.info("\n=== TEST 3: Tenant Stats ===")
    stats = await rag_service.get_tenant_stats(tenant_id)
    logger.info(f"Stats: {stats}")
    
    # Test 4: Simple query
    if has_docs:
        logger.info("\n=== TEST 4: Simple Query ===")
        
        queries = [
            "Qual a potência da luminária HIGHBAY?",
            "Quais produtos vocês vendem?",
            "Qual o preço das luminárias?"
        ]
        
        for query in queries:
            logger.info(f"\nQuery: {query}")
            
            try:
                context = await rag_service.query(
                    tenant_id=tenant_id,
                    query=query,
                    business_context={
                        'project_description': 'Empresa de iluminação LED'
                    }
                )
                
                if "Nothing relevant was found" in context:
                    logger.warning("No relevant context found")
                else:
                    logger.info(f"Context retrieved ({len(context)} chars)")
                    # Show first 200 chars of context
                    logger.info(f"Preview: {context[:200]}...")
            except Exception as e:
                logger.error(f"Query error: {e}")
    
    # Clean up
    await rag_service.close()
    logger.info("\n=== TEST COMPLETED ===")


if __name__ == "__main__":
    asyncio.run(test_rag_simple())
