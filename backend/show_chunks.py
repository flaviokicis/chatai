#!/usr/bin/env python3
"""
Show actual chunks in the vector database with all metadata.
"""

import asyncio
import sys
from uuid import UUID

from app.settings import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession


async def show_chunks(limit: int = 5):
    """Show actual chunks with metadata."""
    
    settings = get_settings()
    tenant_id = UUID("068b37cd-c090-710d-b0b6-5ca37c2887ff")
    
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
    print("CHUNKS IN VECTOR DATABASE (with GPT-5 metadata)")
    print("="*80)
    print(f"\nTenant: {tenant_id}")
    print(f"Showing: First {limit} chunks\n")
    
    async with AsyncSession(engine) as session:
        # Get chunks with their metadata
        result = await session.execute(text("""
            SELECT 
                c.id,
                c.chunk_index,
                c.content,
                c.category,
                c.keywords,
                c.possible_questions,
                c.chunk_metadata,
                d.file_name,
                LENGTH(c.content) as content_length,
                c.embedding IS NOT NULL as has_embedding
            FROM document_chunks c
            JOIN tenant_documents d ON c.document_id = d.id
            WHERE c.tenant_id = :tenant_id
            ORDER BY d.file_name, c.chunk_index
            LIMIT :limit
        """), {"tenant_id": tenant_id, "limit": limit})
        
        chunks = result.fetchall()
        
        if not chunks:
            print("❌ No chunks found!")
            return
        
        for idx, chunk in enumerate(chunks, 1):
            chunk_id, chunk_index, content, category, keywords, possible_questions, \
            chunk_metadata, file_name, content_length, has_embedding = chunk
            
            print("="*80)
            print(f"📦 CHUNK #{idx}")
            print("="*80)
            print(f"🆔 ID: {chunk_id}")
            print(f"📄 Document: {file_name}")
            print(f"📍 Chunk Index: {chunk_index}")
            print(f"📏 Content Length: {content_length} characters")
            print(f"🎯 Has Embedding: {'✅ Yes' if has_embedding else '❌ No'}")
            print()
            
            # GPT-5 Added Metadata
            print("🤖 GPT-5 INTELLIGENT METADATA:")
            print("-" * 40)
            print(f"📂 Category: {category or 'Not categorized'}")
            print(f"🏷️  Keywords: {keywords or 'None'}")
            
            if possible_questions:
                print(f"❓ Possible Questions ({len(possible_questions)} total):")
                for i, question in enumerate(possible_questions[:5], 1):  # Show first 5
                    print(f"   {i}. {question}")
                if len(possible_questions) > 5:
                    print(f"   ... and {len(possible_questions) - 5} more")
            else:
                print("❓ Possible Questions: None")
            
            if chunk_metadata:
                print(f"\n📊 Extra Metadata: {chunk_metadata}")
            
            # Content
            print()
            print("📝 CONTENT:")
            print("-" * 40)
            # Show first 500 chars
            content_preview = content[:500] + "..." if len(content) > 500 else content
            print(content_preview)
            print()
    
    print("="*80)
    print(f"Showing {len(chunks)} of total chunks")
    print("="*80)
    print()
    
    await engine.dispose()


async def show_all_chunks():
    """Show all chunks (compact view)."""
    
    settings = get_settings()
    tenant_id = UUID("068b37cd-c090-710d-b0b6-5ca37c2887ff")
    
    pg_vector_url = settings.pg_vector_database_url
    if pg_vector_url.startswith("postgres://"):
        pg_vector_url = pg_vector_url.replace("postgres://", "postgresql+asyncpg://")
    elif pg_vector_url.startswith("postgresql://"):
        pg_vector_url = pg_vector_url.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(pg_vector_url, echo=False)
    
    print("\n" + "="*80)
    print("ALL CHUNKS - COMPACT VIEW")
    print("="*80 + "\n")
    
    async with AsyncSession(engine) as session:
        result = await session.execute(text("""
            SELECT 
                c.chunk_index,
                c.category,
                d.file_name,
                LENGTH(c.content) as content_length,
                jsonb_array_length(c.possible_questions) as question_count,
                LEFT(c.content, 100) as content_preview
            FROM document_chunks c
            JOIN tenant_documents d ON c.document_id = d.id
            WHERE c.tenant_id = :tenant_id
            ORDER BY d.file_name, c.chunk_index
        """), {"tenant_id": tenant_id})
        
        chunks = result.fetchall()
        
        current_doc = None
        for chunk_index, category, file_name, content_length, question_count, preview in chunks:
            if file_name != current_doc:
                print(f"\n📄 {file_name}")
                print("-" * 60)
                current_doc = file_name
            
            print(f"  Chunk {chunk_index}: [{category or 'general'}] "
                  f"({content_length} chars, {question_count or 0} questions)")
            print(f"    Preview: {preview}...")
            print()
    
    print("="*80 + "\n")
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        try:
            asyncio.run(show_all_chunks())
        except KeyboardInterrupt:
            print("\n❌ Interrupted")
    else:
        limit = int(sys.argv[1]) if len(sys.argv) > 1 else 3
        
        print("\nUsage:")
        print("  python show_chunks.py           # Show first 3 chunks (detailed)")
        print("  python show_chunks.py 5         # Show first 5 chunks (detailed)")
        print("  python show_chunks.py --all     # Show all chunks (compact)")
        print()
        
        try:
            asyncio.run(show_chunks(limit))
        except KeyboardInterrupt:
            print("\n❌ Interrupted")

