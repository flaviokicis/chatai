#!/usr/bin/env python3
"""
Reset vector DB and upload documents to specific tenant.
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.settings import get_settings
from app.services.rag.rag_service import RAGService
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession


async def reset_and_upload():
    """Reset vector DB and upload documents."""
    
    settings = get_settings()
    
    # Configuration
    TENANT_ID = UUID("068b37cd-c090-710d-b0b6-5ca37c2887ff")
    DOCUMENTS = [
        "playground/documents/pdfs/catalogo_luminarias_desordenado.pdf",
        "playground/documents/pdfs/catalogo_de_produtos_led.pdf"
    ]
    
    print("\n" + "="*80)
    print("RESET VECTOR DB AND UPLOAD DOCUMENTS")
    print("="*80 + "\n")
    
    # Get vector DB URL
    pg_vector_url = settings.pg_vector_database_url
    if not pg_vector_url:
        print("❌ PG_VECTOR_DATABASE_URL not configured!")
        return
    
    # Convert to async URL
    if pg_vector_url.startswith("postgres://"):
        pg_vector_url = pg_vector_url.replace("postgres://", "postgresql+asyncpg://")
    elif pg_vector_url.startswith("postgresql://"):
        pg_vector_url = pg_vector_url.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(pg_vector_url, echo=False)
    
    # Step 1: Clear all vector DB data
    print("🗑️  Step 1: Clearing ALL vector database data...")
    async with AsyncSession(engine) as session:
        # Delete in order due to foreign keys
        await session.execute(text("DELETE FROM retrieval_sessions"))
        print("   ✓ Cleared retrieval sessions")
        
        await session.execute(text("DELETE FROM chunk_relationships"))
        print("   ✓ Cleared chunk relationships")
        
        await session.execute(text("DELETE FROM document_chunks"))
        print("   ✓ Cleared document chunks")
        
        await session.execute(text("DELETE FROM tenant_documents"))
        print("   ✓ Cleared tenant documents")
        
        await session.commit()
    
    print("✅ Vector DB completely cleared!\n")
    
    # Step 2: Initialize RAG service
    print(f"📤 Step 2: Uploading documents to tenant {TENANT_ID}...")
    
    rag_service = RAGService(
        openai_api_key=settings.openai_api_key,
        vector_db_url=settings.pg_vector_database_url,
        max_retrieval_attempts=3
    )
    
    # Wait for initialization
    await asyncio.sleep(1)
    
    # Step 3: Upload each document
    for doc_path in DOCUMENTS:
        file_path = Path(doc_path)
        
        if not file_path.exists():
            print(f"   ❌ File not found: {file_path}")
            continue
        
        print(f"\n   📄 Uploading: {file_path.name}")
        
        try:
            metadata = {
                "original_filename": file_path.name,
                "tenant_id": str(TENANT_ID),
                "upload_source": "reset_script"
            }
            
            result = await rag_service.save_document(
                tenant_id=TENANT_ID,
                file_path=str(file_path),
                metadata=metadata
            )
            
            if result.get('success'):
                print(f"      ✅ Success!")
                print(f"      📊 Chunks created: {result.get('chunks_created', 0)}")
                print(f"      📝 Total words: {result.get('total_words', 0)}")
                print(f"      🆔 Document ID: {result.get('document_id')}")
            else:
                print(f"      ❌ Failed: {result.get('error')}")
                
        except Exception as e:
            print(f"      ❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    # Step 4: Verify results
    print("\n" + "="*80)
    print("VERIFICATION")
    print("="*80 + "\n")
    
    async with AsyncSession(engine) as session:
        result = await session.execute(text("""
            SELECT 
                d.file_name,
                d.file_type,
                COUNT(c.id) as chunk_count,
                AVG(LENGTH(c.content)) as avg_chunk_size
            FROM tenant_documents d
            LEFT JOIN document_chunks c ON d.id = c.document_id
            WHERE d.tenant_id = :tenant_id
            GROUP BY d.id, d.file_name, d.file_type
            ORDER BY d.created_at DESC
        """), {"tenant_id": TENANT_ID})
        
        docs = result.fetchall()
        
        if docs:
            print(f"✅ Successfully stored {len(docs)} document(s):\n")
            for file_name, file_type, chunk_count, avg_size in docs:
                print(f"   📄 {file_name}")
                print(f"      Type: {file_type}")
                print(f"      Chunks: {chunk_count or 0}")
                print(f"      Avg chunk size: {int(avg_size or 0)} chars")
                print()
        else:
            print("❌ No documents found! Upload may have failed.")
    
    print("="*80)
    print("DONE!")
    print("="*80 + "\n")
    
    await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(reset_and_upload())
    except KeyboardInterrupt:
        print("\n❌ Interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

