#!/usr/bin/env python3
"""Initialize pgvector database tables for RAG system.

This script creates the necessary tables in the PG_VECTOR_DATABASE_URL database,
which is completely separate from the main application database.
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def drop_vector_tables():
    """Drop existing vector database tables."""
    
    pg_vector_url = os.getenv("PG_VECTOR_DATABASE_URL")
    if not pg_vector_url:
        logger.error("PG_VECTOR_DATABASE_URL not set")
        return
    
    # Convert to async URL
    if pg_vector_url.startswith("postgres://"):
        pg_vector_url = pg_vector_url.replace("postgres://", "postgresql+asyncpg://")
    elif pg_vector_url.startswith("postgresql://"):
        pg_vector_url = pg_vector_url.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(pg_vector_url, echo=False)
    
    async with engine.begin() as conn:
        logger.info("Dropping existing tables...")
        await conn.execute(text("DROP TABLE IF EXISTS retrieval_sessions CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS chunk_relationships CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS document_chunks CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS tenant_documents CASCADE"))
        logger.info("Tables dropped")
    
    await engine.dispose()


async def init_vector_database():
    """Initialize the pgvector database with necessary tables."""
    
    # Get the pgvector database URL
    pg_vector_url = os.getenv("PG_VECTOR_DATABASE_URL")
    if not pg_vector_url:
        logger.error("PG_VECTOR_DATABASE_URL not set in environment")
        sys.exit(1)
    
    # Convert to async URL
    if pg_vector_url.startswith("postgres://"):
        pg_vector_url = pg_vector_url.replace("postgres://", "postgresql+asyncpg://")
    elif pg_vector_url.startswith("postgresql://"):
        pg_vector_url = pg_vector_url.replace("postgresql://", "postgresql+asyncpg://")
    
    logger.info("Connecting to pgvector database...")
    engine = create_async_engine(pg_vector_url, echo=True)
    
    async with engine.begin() as conn:
        logger.info("Enabling pgvector extension...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        logger.info("Creating tenant_documents table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tenant_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                file_type VARCHAR(50) NOT NULL,
                file_size INTEGER,
                raw_content TEXT,
                parsed_content TEXT,
                document_metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
            )
        """))
        
        logger.info("Creating document_chunks table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID NOT NULL REFERENCES tenant_documents(id) ON DELETE CASCADE,
                tenant_id UUID NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding vector(2000),
                chunk_metadata JSONB,
                category VARCHAR(100),
                keywords TEXT,
                possible_questions JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
            )
        """))
        
        logger.info("Creating chunk_relationships table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chunk_relationships (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
                target_chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
                relationship_type VARCHAR(50) NOT NULL,
                relationship_reason TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                UNIQUE(source_chunk_id, target_chunk_id, relationship_type)
            )
        """))
        
        logger.info("Creating retrieval_sessions table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS retrieval_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                thread_id UUID,
                query TEXT NOT NULL,
                query_embedding vector(2000),
                retrieved_chunks JSONB,
                final_context TEXT,
                attempts INTEGER DEFAULT 0,
                sufficient BOOLEAN DEFAULT FALSE,
                judge_reasoning TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
            )
        """))
        
        # Create indexes
        logger.info("Creating indexes...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_tenant_documents_tenant_id 
            ON tenant_documents(tenant_id)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_id 
            ON document_chunks(tenant_id)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id 
            ON document_chunks(document_id)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_category 
            ON document_chunks(category)
        """))
        
        # Create vector indexes for similarity search
        # Using ivfflat index for 2000 dimensions (pgvector limit)
        logger.info("Creating vector indexes...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding 
            ON document_chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_retrieval_sessions_query_embedding 
            ON retrieval_sessions USING ivfflat (query_embedding vector_cosine_ops)
            WITH (lists = 100)
        """))
        
    logger.info("✅ Vector database initialized successfully!")
    await engine.dispose()


async def check_vector_database():
    """Check if vector database is properly initialized."""
    
    pg_vector_url = os.getenv("PG_VECTOR_DATABASE_URL")
    if not pg_vector_url:
        logger.error("PG_VECTOR_DATABASE_URL not set")
        return False
    
    # Convert to async URL
    if pg_vector_url.startswith("postgres://"):
        pg_vector_url = pg_vector_url.replace("postgres://", "postgresql+asyncpg://")
    elif pg_vector_url.startswith("postgresql://"):
        pg_vector_url = pg_vector_url.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(pg_vector_url, echo=False)
    
    try:
        async with engine.begin() as conn:
            # Check if pgvector extension exists
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'vector'
                )
            """))
            has_vector = result.scalar()
            
            if not has_vector:
                logger.warning("pgvector extension not found")
                return False
            
            # Check if tables exist
            tables = ["tenant_documents", "document_chunks", "chunk_relationships", "retrieval_sessions"]
            for table in tables:
                result = await conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = '{table}'
                    )
                """))
                if not result.scalar():
                    logger.warning(f"Table {table} not found")
                    return False
            
            logger.info("✅ All vector database tables exist")
            return True
            
    except Exception as e:
        logger.error(f"Error checking vector database: {e}")
        return False
    finally:
        await engine.dispose()


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialize pgvector database")
    parser.add_argument("--check", action="store_true", help="Check if database is initialized")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables")
    args = parser.parse_args()
    
    if args.check:
        is_ready = await check_vector_database()
        sys.exit(0 if is_ready else 1)
    elif args.reset:
        await drop_vector_tables()
        await init_vector_database()
    else:
        await init_vector_database()


if __name__ == "__main__":
    asyncio.run(main())
