#!/usr/bin/env python3
"""
Quick script to list all documents in the RAG database.
"""

import asyncio
import os
import sys
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.settings import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession


async def list_documents():
    """List all documents in the RAG database."""
    
    settings = get_settings()
    
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
    
    print("\n" + "="*80)
    print("RAG DOCUMENTS IN DATABASE")
    print("="*80 + "\n")
    
    # Get all tenants with documents
    async with AsyncSession(engine) as session:
        result = await session.execute(text("""
            SELECT DISTINCT 
                d.tenant_id,
                COUNT(DISTINCT d.id) as doc_count,
                COUNT(DISTINCT c.id) as chunk_count
            FROM tenant_documents d
            LEFT JOIN document_chunks c ON d.id = c.document_id
            GROUP BY d.tenant_id
            ORDER BY doc_count DESC
        """))
        
        tenants = result.fetchall()
        
        if not tenants:
            print("📭 No documents uploaded yet!\n")
            return
        
        total_docs = 0
        total_chunks = 0
        
        # Show each tenant's documents
        for tenant_id, doc_count, chunk_count in tenants:
            total_docs += doc_count
            total_chunks += chunk_count or 0
            
            print(f"📁 Tenant: {tenant_id}")
            print(f"   Documents: {doc_count}")
            print(f"   Chunks: {chunk_count or 0}")
            print()
            
            # Get documents for this tenant
            result = await session.execute(text("""
                SELECT 
                    d.id,
                    d.file_name,
                    d.file_type,
                    d.file_size,
                    d.created_at,
                    COUNT(c.id) as chunk_count
                FROM tenant_documents d
                LEFT JOIN document_chunks c ON d.id = c.document_id
                WHERE d.tenant_id = :tenant_id
                GROUP BY d.id, d.file_name, d.file_type, d.file_size, d.created_at
                ORDER BY d.created_at DESC
            """), {"tenant_id": tenant_id})
            
            docs = result.fetchall()
            
            for doc_id, file_name, file_type, file_size, created_at, chunks in docs:
                size_kb = (file_size or 0) / 1024
                print(f"   📄 {file_name}")
                print(f"      ID: {doc_id}")
                print(f"      Type: {file_type}")
                print(f"      Size: {size_kb:.1f} KB")
                print(f"      Chunks: {chunks or 0}")
                print(f"      Uploaded: {created_at.strftime('%Y-%m-%d %H:%M:%S')}")
                print()
        
        print("="*80)
        print(f"TOTAL: {total_docs} documents, {total_chunks} chunks across {len(tenants)} tenant(s)")
        print("="*80 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(list_documents())
    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

