#!/usr/bin/env python3
"""Re-upload documents with GPT-5 intelligent chunking."""

import asyncio
import logging
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).parent))

from app.services.rag import RAGService
from app.settings import get_settings
from app.db.session import db_session

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

async def clear_existing_chunks(tenant_id: str):
    """Clear existing chunks for the tenant."""
    settings = get_settings()
    db_url = settings.vector_database_url
    
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql+asyncpg://')
    elif db_url.startswith('postgresql://'):
        db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://')
    
    engine = create_async_engine(db_url)
    
    async with engine.begin() as conn:
        # Delete existing chunks
        await conn.execute(text("""
            DELETE FROM document_chunks 
            WHERE tenant_id = :tenant_id
        """), {"tenant_id": tenant_id})
        
        # Delete existing documents
        await conn.execute(text("""
            DELETE FROM tenant_documents 
            WHERE tenant_id = :tenant_id
        """), {"tenant_id": tenant_id})
        
        logger.info(f"Cleared existing documents for tenant {tenant_id}")
    
    await engine.dispose()


async def upload_documents_with_gpt5():
    """Upload documents using GPT-5 intelligent chunking."""
    
    settings = get_settings()
    tenant_id = "44b613e6-c5a2-4f41-bae0-05b168245ac7"
    
    print("\n" + "=" * 80)
    print("RE-UPLOADING DOCUMENTS WITH GPT-5 INTELLIGENT CHUNKING")
    print("=" * 80)
    
    # Clear existing chunks
    print("\n1. Clearing existing chunks...")
    await clear_existing_chunks(tenant_id)
    
    # Initialize RAG service
    print("\n2. Initializing RAG service with GPT-5...")
    rag_service = RAGService(
        openai_api_key=settings.openai_api_key,
        vector_db_url=settings.vector_database_url,
        max_retrieval_attempts=3
    )
    
    await asyncio.sleep(1)
    
    # Documents to upload
    documents = [
        {
            'path': 'playground/documents/catalogo_de_produtos_led.md',
            'name': 'Catálogo de Produtos LED'
        },
        {
            'path': 'playground/documents/pdfs/catalogo_luminarias_desordenado.pdf',
            'name': 'Catálogo Luminárias PDF'
        }
    ]
    
    # Upload documents
    print("\n3. Uploading documents with GPT-5 intelligent chunking...")
    print("-" * 60)
    
    for doc in documents:
        doc_path = Path(doc['path'])
        
        if not doc_path.exists():
            print(f"❌ File not found: {doc_path}")
            continue
        
        print(f"\nUploading: {doc['name']}")
        print(f"File: {doc_path}")
        
        try:
            result = await rag_service.save_document(
                tenant_id=tenant_id,
                file_path=str(doc_path),
                metadata={
                    'source': 'gpt5_reupload',
                    'name': doc['name']
                }
            )
            
            if result.get('success'):
                print(f"✅ Success!")
                print(f"   - Document ID: {result.get('document_id')}")
                print(f"   - Chunks created: {result.get('chunks_created')}")
                print(f"   - Relationships: {result.get('relationships_created')}")
                print(f"   - Total words: {result.get('total_words')}")
            else:
                print(f"❌ Failed: {result.get('error')}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Test retrieval with new chunks
    print("\n4. Testing retrieval with new GPT-5 chunks...")
    print("-" * 60)
    
    test_queries = [
        'CP-200 26.000 lumens',
        'luminária HIGHBAY HB-200 30.000 lumens',
        'garantia 5 anos condições',
        'proteção IP66 área classificada'
    ]
    
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        
        try:
            context = await asyncio.wait_for(
                rag_service.query(
                    tenant_id=tenant_id,
                    query=query,
                    business_context={'project_description': 'Iluminação LED'}
                ),
                timeout=15.0
            )
            
            if context and 'Nothing relevant' not in context and 'Error' not in context:
                print(f"✅ Context found ({len(context)} chars)")
            else:
                print("❌ No relevant context")
                
        except asyncio.TimeoutError:
            print("⏱️ Timeout")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    await rag_service.close()
    
    print("\n" + "=" * 80)
    print("✅ DOCUMENTS RE-UPLOADED WITH GPT-5 INTELLIGENT CHUNKING!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(upload_documents_with_gpt5())

