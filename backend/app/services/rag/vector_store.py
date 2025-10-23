"""Vector store repository for pgvector operations.

This module provides database operations for storing and retrieving
document embeddings using pgvector.
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import ChunkRelationship, DocumentChunk, RetrievalSession, TenantDocument

logger = logging.getLogger(__name__)


class ChunkResult:
    """Represents a chunk retrieved from vector search."""
    
    def __init__(
        self,
        chunk_id: UUID,
        content: str,
        score: float,
        metadata: dict | None = None,
        category: str | None = None,
        keywords: str | None = None,
        possible_questions: list[str] | None = None,
        document_name: str | None = None
    ):
        self.chunk_id = chunk_id
        self.content = content
        self.score = score
        self.metadata = metadata or {}
        self.category = category
        self.keywords = keywords
        self.possible_questions = possible_questions or []
        self.document_name = document_name


class VectorStoreRepository:
    """Repository for vector storage operations using pgvector.
    
    This repository handles all database operations related to document
    chunks and their embeddings.
    """
    
    def __init__(self, database_url: str):
        """Initialize the vector store repository.
        
        Args:
            database_url: PostgreSQL database URL with pgvector extension
        """
        # Convert to async URL if needed
        if database_url.startswith("postgres://"):
            # Handle old-style postgres:// URLs
            database_url = database_url.replace("postgres://", "postgresql+asyncpg://")
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
        elif database_url.startswith("postgresql+psycopg://"):
            database_url = database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
        
        self.engine = create_async_engine(
            database_url,
            echo=False,
            pool_size=30,
            max_overflow=50,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
    
    async def initialize(self):
        """Initialize the vector store (ensure extension is enabled)."""
        async with self.engine.begin() as conn:
            # Ensure pgvector extension is enabled
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            logger.info("Pgvector extension initialized")
    
    async def store_document(
        self,
        tenant_id: UUID,
        file_name: str,
        file_type: str,
        raw_content: str,
        parsed_content: str,
        metadata: dict | None = None
    ) -> UUID:
        """Store a document in the database.
        
        Args:
            tenant_id: Tenant UUID
            file_name: Name of the document file
            file_type: Type of document (pdf, txt, etc)
            raw_content: Original document content
            parsed_content: Cleaned/parsed content
            metadata: Optional metadata
            
        Returns:
            Document UUID
        """
        async with self.async_session() as session:
            document = TenantDocument(
                tenant_id=tenant_id,
                file_name=file_name,
                file_type=file_type,
                raw_content=raw_content,
                parsed_content=parsed_content,
                document_metadata=metadata or {},
                file_size=len(raw_content.encode("utf-8"))
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)
            return document.id
    
    async def store_chunks(
        self,
        document_id: UUID,
        tenant_id: UUID,
        chunks: list[dict]
    ) -> list[UUID]:
        """Store document chunks with embeddings.
        
        Args:
            document_id: Parent document UUID
            tenant_id: Tenant UUID
            chunks: List of chunk dictionaries with content, embedding, metadata
            
        Returns:
            List of chunk UUIDs
        """
        chunk_ids = []
        
        async with self.async_session() as session:
            for idx, chunk_data in enumerate(chunks):
                # Store chunk in regular table
                chunk = DocumentChunk(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    chunk_index=idx,
                    content=chunk_data["content"],
                    chunk_metadata=chunk_data.get("metadata", {}),
                    category=chunk_data.get("category"),
                    keywords=chunk_data.get("keywords"),
                    possible_questions=chunk_data.get("possible_questions", [])
                )
                session.add(chunk)
                await session.flush()  # Get the ID
                chunk_ids.append(chunk.id)
                
                # Store embedding using raw SQL for pgvector
                if chunk_data.get("embedding"):
                    embedding = chunk_data["embedding"]
                    # Format embedding as PostgreSQL array literal
                    embedding_str = f'[{",".join(map(str, embedding))}]'
                    await session.execute(
                        text(f"""
                            UPDATE document_chunks 
                            SET embedding = '{embedding_str}'::vector 
                            WHERE id = :chunk_id
                        """),
                        {"chunk_id": chunk.id}
                    )
            
            await session.commit()
        
        return chunk_ids
    
    async def store_chunk_relationships(
        self,
        relationships: list[tuple[UUID, UUID, str, str]]
    ):
        """Store relationships between chunks.
        
        Args:
            relationships: List of (source_id, target_id, relationship_type, reason)
        """
        async with self.async_session() as session:
            for source_id, target_id, rel_type, reason in relationships:
                relationship = ChunkRelationship(
                    source_chunk_id=source_id,
                    target_chunk_id=target_id,
                    relationship_type=rel_type,
                    relationship_reason=reason
                )
                session.add(relationship)
            await session.commit()
    
    async def search_similar_chunks(
        self,
        tenant_id: UUID,
        query_embedding: list[float],
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> list[ChunkResult]:
        """Search for similar chunks using vector similarity.
        
        Args:
            tenant_id: Tenant UUID
            query_embedding: Query embedding vector
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of ChunkResult objects
        """
        async with self.async_session() as session:
            # Use raw SQL for pgvector operations
            # Format embedding as PostgreSQL array literal
            embedding_str = f'[{",".join(map(str, query_embedding))}]'
            query = text(f"""
                SELECT 
                    c.id,
                    c.content,
                    c.chunk_metadata,
                    c.category,
                    c.keywords,
                    c.possible_questions,
                    d.file_name,
                    1 - (c.embedding <=> '{embedding_str}'::vector) as similarity
                FROM document_chunks c
                JOIN tenant_documents d ON c.document_id = d.id
                WHERE c.tenant_id = :tenant_id
                    AND c.embedding IS NOT NULL
                    AND 1 - (c.embedding <=> '{embedding_str}'::vector) >= :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            
            result = await session.execute(
                query,
                {
                    "tenant_id": tenant_id,
                    "threshold": similarity_threshold,
                    "limit": limit
                }
            )
            
            chunks = []
            for row in result:
                chunks.append(ChunkResult(
                    chunk_id=row.id,
                    content=row.content,
                    score=row.similarity,
                    metadata=row.chunk_metadata,
                    category=row.category,
                    keywords=row.keywords,
                    possible_questions=row.possible_questions,
                    document_name=row.file_name
                ))
            
            return chunks
    
    async def get_related_chunks(
        self,
        chunk_ids: list[UUID],
        relationship_types: list[str] | None = None
    ) -> list[ChunkResult]:
        """Get chunks related to the given chunk IDs.
        
        Args:
            chunk_ids: List of source chunk IDs
            relationship_types: Optional filter for relationship types
            
        Returns:
            List of related ChunkResult objects
        """
        async with self.async_session() as session:
            query = select(DocumentChunk).join(
                ChunkRelationship,
                or_(
                    DocumentChunk.id == ChunkRelationship.target_chunk_id,
                    DocumentChunk.id == ChunkRelationship.source_chunk_id
                )
            ).where(
                or_(
                    ChunkRelationship.source_chunk_id.in_(chunk_ids),
                    ChunkRelationship.target_chunk_id.in_(chunk_ids)
                )
            )
            
            if relationship_types:
                query = query.where(
                    ChunkRelationship.relationship_type.in_(relationship_types)
                )
            
            result = await session.execute(query.distinct())
            chunks = result.scalars().all()
            
            return [
                ChunkResult(
                    chunk_id=chunk.id,
                    content=chunk.content,
                    score=1.0,  # Related chunks get full score
                    metadata=chunk.chunk_metadata,
                    category=chunk.category,
                    keywords=chunk.keywords,
                    possible_questions=chunk.possible_questions
                )
                for chunk in chunks
                if chunk.id not in chunk_ids  # Exclude source chunks
            ]
    
    async def has_documents(self, tenant_id: UUID) -> bool:
        """Check if tenant has any documents stored.
        
        Args:
            tenant_id: Tenant UUID
            
        Returns:
            True if tenant has documents, False otherwise
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(TenantDocument).where(
                    TenantDocument.tenant_id == tenant_id
                ).limit(1)
            )
            return result.scalar() is not None
    
    async def save_retrieval_session(
        self,
        tenant_id: UUID,
        query: str,
        query_embedding: list[float] | None,
        retrieved_chunks: list[dict],
        final_context: str,
        attempts: int,
        sufficient: bool,
        judge_reasoning: str,
        thread_id: UUID | None = None
    ) -> UUID:
        """Save a retrieval session for analytics.
        
        Args:
            tenant_id: Tenant UUID
            query: User query
            query_embedding: Query embedding vector
            retrieved_chunks: List of chunk data
            final_context: Context sent to LLM
            attempts: Number of retrieval attempts
            sufficient: Whether chunks were sufficient
            judge_reasoning: Judge's reasoning
            thread_id: Optional chat thread ID
            
        Returns:
            RetrievalSession UUID
        """
        async with self.async_session() as session:
            retrieval_session = RetrievalSession(
                tenant_id=tenant_id,
                thread_id=thread_id,
                query=query,
                retrieved_chunks=retrieved_chunks,
                final_context=final_context,
                attempts=attempts,
                sufficient=sufficient,
                judge_reasoning=judge_reasoning
            )
            session.add(retrieval_session)
            await session.flush()
            
            # Store query embedding using raw SQL
            if query_embedding:
                embedding_str = f'[{",".join(map(str, query_embedding))}]'
                await session.execute(
                    text(f"""
                        UPDATE retrieval_sessions 
                        SET query_embedding = '{embedding_str}'::vector 
                        WHERE id = :session_id
                    """),
                    {"session_id": retrieval_session.id}
                )
            
            await session.commit()
            return retrieval_session.id
    
    async def get_tenant_chunks_count(self, tenant_id: UUID) -> int:
        """Get the total number of chunks for a tenant.
        
        Args:
            tenant_id: Tenant UUID
            
        Returns:
            Number of chunks
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.tenant_id == tenant_id
                )
            )
            return len(result.scalars().all())
    
    async def get_documents_summary(self, tenant_id: UUID) -> list[dict]:
        """Get summary information for all documents belonging to a tenant.
        
        Args:
            tenant_id: Tenant UUID
            
        Returns:
            List of document summaries without chunk payloads
        """
        async with self.async_session() as session:
            query = text("""
                SELECT 
                    d.id,
                    d.file_name,
                    d.file_type,
                    d.file_size,
                    d.created_at,
                    COUNT(c.id) AS chunk_count
                FROM tenant_documents d
                LEFT JOIN document_chunks c ON d.id = c.document_id
                WHERE d.tenant_id = :tenant_id
                GROUP BY d.id, d.file_name, d.file_type, d.file_size, d.created_at
                ORDER BY d.created_at DESC
            """)
            
            result = await session.execute(query, {"tenant_id": tenant_id})
            rows = result.fetchall()
            
            summaries = []
            for row in rows:
                summaries.append({
                    "id": row.id,
                    "file_name": row.file_name,
                    "file_type": row.file_type,
                    "file_size": row.file_size,
                    "created_at": row.created_at,
                    "chunk_count": int(row.chunk_count or 0),
                })
            
            return summaries
    
    async def get_document_details(
        self,
        tenant_id: UUID,
        document_id: UUID
    ) -> dict | None:
        """Get a single document with its chunk details.
        
        Args:
            tenant_id: Tenant UUID
            document_id: Document UUID
            
        Returns:
            Document dictionary with chunk payload or None if not found
        """
        async with self.async_session() as session:
            doc_result = await session.execute(
                select(TenantDocument).where(
                    TenantDocument.id == document_id,
                    TenantDocument.tenant_id == tenant_id,
                )
            )
            document = doc_result.scalar_one_or_none()
            if not document:
                return None
            
            chunk_result = await session.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            )
            chunks = chunk_result.scalars().all()
            
            chunk_payload = []
            for chunk in chunks:
                chunk_payload.append({
                    "id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "category": chunk.category,
                    "keywords": chunk.keywords,
                    "possible_questions": chunk.possible_questions,
                    "metadata": chunk.chunk_metadata or {},
                    "created_at": chunk.created_at,
                    "updated_at": chunk.updated_at,
                })
            
            return {
                "id": document.id,
                "tenant_id": document.tenant_id,
                "file_name": document.file_name,
                "file_type": document.file_type,
                "file_size": document.file_size,
                "created_at": document.created_at,
                "updated_at": document.updated_at,
                "metadata": document.document_metadata or {},
                "chunk_count": len(chunk_payload),
                "chunks": chunk_payload,
            }
    
    async def delete_document(self, tenant_id: UUID, document_id: UUID) -> bool:
        """Delete a document and all its chunks if it belongs to the tenant.
        
        Args:
            tenant_id: Tenant UUID
            document_id: Document UUID to delete
            
        Returns:
            True if the document was deleted, False otherwise
        """
        async with self.async_session() as session:
            document = await session.get(TenantDocument, document_id)
            if not document or document.tenant_id != tenant_id:
                return False
            
            await session.delete(document)
            await session.commit()
            return True
    
    async def update_document_metadata(
        self, tenant_id: UUID, document_id: UUID, metadata: dict[str, Any]
    ) -> bool:
        """Update metadata for a document.
        
        Args:
            tenant_id: Tenant UUID
            document_id: Document UUID to update
            metadata: New metadata dictionary
            
        Returns:
            True if the update was successful, False otherwise
        """
        async with self.async_session() as session:
            document = await session.get(TenantDocument, document_id)
            if not document or document.tenant_id != tenant_id:
                return False
            
            document.metadata = metadata
            document.updated_at = datetime.utcnow()
            await session.commit()
            return True
    
    async def get_tenant_documents(self, tenant_id: UUID) -> list[dict]:
        """Get all documents with chunk info for a tenant.
        
        Args:
            tenant_id: Tenant UUID
            
        Returns:
            List of document dictionaries with chunk info
        """
        async with self.async_session() as session:
            # Get documents with chunk count
            query = text("""
                SELECT 
                    d.id, d.file_name, d.file_type, d.file_size, d.created_at,
                    COUNT(c.id) as chunk_count,
                    ARRAY_AGG(
                        jsonb_build_object(
                            'id', c.id,
                            'content', c.content,
                            'category', c.category,
                            'chunk_index', c.chunk_index
                        ) ORDER BY c.chunk_index
                    ) FILTER (WHERE c.id IS NOT NULL) as chunks
                FROM tenant_documents d
                LEFT JOIN document_chunks c ON d.id = c.document_id
                WHERE d.tenant_id = :tenant_id
                GROUP BY d.id, d.file_name, d.file_type, d.file_size, d.created_at
                ORDER BY d.created_at DESC
            """)
            
            result = await session.execute(query, {"tenant_id": tenant_id})
            rows = result.fetchall()
            
            documents = []
            for row in rows:
                documents.append({
                    "id": row.id,
                    "file_name": row.file_name,
                    "file_type": row.file_type,
                    "file_size": row.file_size,
                    "created_at": row.created_at,
                    "chunk_count": row.chunk_count,
                    "chunks": row.chunks or []
                })
            
            return documents
    
    async def get_indexes(self) -> list[dict]:
        """Get all indexes in the vector database.
        
        Returns:
            List of index information dictionaries
        """
        async with self.async_session() as session:
            query = text("""
                SELECT 
                    i.indexname,
                    i.tablename,
                    CASE 
                        WHEN i.indexdef LIKE '%USING ivfflat%' THEN 'ivfflat'
                        WHEN i.indexdef LIKE '%USING hnsw%' THEN 'hnsw'
                        WHEN i.indexdef LIKE '%USING btree%' THEN 'btree'
                        ELSE 'other'
                    END as index_type,
                    CASE 
                        WHEN i.indexdef LIKE '%embedding%' THEN 'embedding'
                        WHEN i.indexdef LIKE '%tenant_id%' THEN 'tenant_id'
                        WHEN i.indexdef LIKE '%document_id%' THEN 'document_id'
                        ELSE 'other'
                    END as column
                FROM pg_indexes i
                WHERE i.schemaname = 'public'
                AND i.tablename IN ('tenant_documents', 'document_chunks', 'chunk_relationships', 'retrieval_sessions')
                ORDER BY i.tablename, i.indexname
            """)
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            indexes = []
            for row in rows:
                indexes.append({
                    "indexname": row.indexname,
                    "tablename": row.tablename,
                    "index_type": row.index_type,
                    "column": row.column
                })
            
            return indexes
    
    async def get_chunk_count(self, tenant_id: UUID) -> int:
        """Get total number of chunks for a tenant.
        
        Args:
            tenant_id: Tenant UUID
            
        Returns:
            Total chunk count
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(func.count(DocumentChunk.id))
                .where(DocumentChunk.tenant_id == tenant_id)
            )
            return result.scalar() or 0
    
    async def clear_tenant_documents(self, tenant_id: UUID):
        """Clear all documents and chunks for a tenant.
        
        Args:
            tenant_id: Tenant UUID
        """
        async with self.async_session() as session:
            # Delete all documents for the tenant (cascades to chunks and relationships)
            result = await session.execute(
                select(TenantDocument).where(TenantDocument.tenant_id == tenant_id)
            )
            documents = result.scalars().all()
            
            for document in documents:
                await session.delete(document)
            
            await session.commit()
            logger.info(f"Cleared {len(documents)} documents for tenant {tenant_id}")
    
    async def close(self):
        """Close the database connection."""
        await self.engine.dispose()
