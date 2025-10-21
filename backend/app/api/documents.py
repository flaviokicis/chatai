"""
API endpoints for tenant document management.

Provides endpoints for:
- Uploading documents for RAG
- Listing tenant documents
- Deleting documents
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi import Path as PathParam
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.app_context import get_app_context
from app.db.models import TenantProjectConfig
from app.db.session import get_db_session
from app.services.rag.rag_service import RAGService

logger = logging.getLogger(__name__)

# Mounted under the aggregated API router with prefix "/api"
# Final path: /api/tenants/{tenant_id}/documents
router = APIRouter(prefix="/tenants/{tenant_id}/documents", tags=["documents"])


class DocumentUploadResponse(BaseModel):
    """Response model for document upload."""
    
    success: bool
    message: str
    document_id: str | None = None
    chunks_created: int = 0
    total_words: int = 0
    error: str | None = None


class DocumentStatusResponse(BaseModel):
    """Response model for document status check."""
    
    has_documents: bool
    document_count: int = 0
    total_chunks: int = 0


class DocumentSummaryResponse(BaseModel):
    """Summary information for a document."""

    id: UUID
    file_name: str
    file_type: str
    file_size: int | None = None
    created_at: datetime
    chunk_count: int


class DocumentChunkResponse(BaseModel):
    """Chunk payload returned in document detail views."""

    id: UUID
    chunk_index: int
    content: str
    category: str | None = None
    keywords: str | None = None
    possible_questions: list[str] | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentDetailResponse(DocumentSummaryResponse):
    """Full document payload including metadata and chunks."""

    updated_at: datetime | None = None
    metadata: dict[str, Any] | None = None
    chunks: list[DocumentChunkResponse]


class DocumentListResponse(BaseModel):
    """Response model for listing documents."""

    documents: list[DocumentSummaryResponse]
    total_count: int


class DocumentDeleteResponse(BaseModel):
    """Response model for document deletion."""

    success: bool
    message: str


class UpdateMetadataRequest(BaseModel):
    """Request model for updating document metadata."""

    metadata: dict[str, Any]


class UpdateMetadataResponse(BaseModel):
    """Response model for metadata update."""

    success: bool
    message: str


class DocumentQueryRequest(BaseModel):
    """Request payload for testing RAG queries."""

    query: str


class DocumentQueryChunk(BaseModel):
    """Chunk returned in a RAG query response."""

    id: UUID
    content: str
    score: float
    category: str | None = None
    keywords: str | None = None
    possible_questions: list[str] | None = None
    metadata: dict[str, Any] | None = None
    document_name: str | None = None


class DocumentQueryResponse(BaseModel):
    """Response payload for testing RAG queries."""

    success: bool
    no_documents: bool
    context: str | None
    judge_reasoning: str | None = None
    attempts: int
    sufficient: bool
    chunks: list[DocumentQueryChunk]
    error: str | None = None
    generated_answer: str | None = None


def _get_rag_service(request: Request) -> RAGService:
    """Get RAG service from app context or raise error."""
    ctx = get_app_context(request.app)
    if not ctx.rag_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service is not configured. Please set PG_VECTOR_DATABASE_URL and OPENAI_API_KEY."
        )
    return ctx.rag_service


def _validate_tenant(tenant_id: UUID, session: Session) -> TenantProjectConfig | None:
    """Validate that tenant exists and return config if available."""
    tenant = session.query(TenantProjectConfig).filter_by(id=tenant_id).first()
    return tenant


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    request: Request,
    tenant_id: UUID = PathParam(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
) -> DocumentUploadResponse:
    """Upload a document for RAG processing.
    
    Supports:
    - PDF files
    - Text files (.txt, .md)
    - JSON files
    
    The document will be:
    1. Parsed to extract text content
    2. Intelligently chunked
    3. Embedded using OpenAI text-embedding-3-large
    4. Stored in pgvector for retrieval
    """

    # Validate tenant exists
    tenant = _validate_tenant(tenant_id, session)
    
    # Get RAG service
    rag_service = _get_rag_service(request)
    
    # Validate file type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided"
        )
    
    allowed_extensions = {".pdf", ".txt", ".md", ".json"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed types: {', '.join(allowed_extensions)}"
        )
    
    # Check file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 10MB."
        )
    
    # Save file temporarily
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            tmp_file.write(contents)
            tmp_path = tmp_file.name
        
        # Process with RAG service
        logger.info(f"Processing document upload for tenant {tenant_id}: {file.filename}")
        
        # Add metadata
        metadata = {
            "original_filename": file.filename,
            "tenant_id": str(tenant_id),
            "business_name": tenant.business_name if tenant else None,
        }
        
        result = await rag_service.save_document(
            tenant_id=tenant_id,
            file_path=tmp_path,
            metadata=metadata
        )
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        if result.get("success"):
            return DocumentUploadResponse(
                success=True,
                message=f"Document '{file.filename}' uploaded successfully",
                document_id=result.get("document_id"),
                chunks_created=result.get("chunks_created", 0),
                total_words=result.get("total_words", 0)
            )
        return DocumentUploadResponse(
            success=False,
            message="Failed to process document",
            error=result.get("error", "Unknown error occurred")
        )
            
    except Exception as e:
        logger.error(f"Error uploading document for tenant {tenant_id}: {e}")
        # Clean up temp file if it exists
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {e!s}"
        )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    tenant_id: UUID = PathParam(...),
    session: Session = Depends(get_db_session),
) -> DocumentListResponse:
    """List documents uploaded for a tenant."""

    _validate_tenant(tenant_id, session)
    rag_service = _get_rag_service(request)

    try:
        summaries = await rag_service.list_documents(tenant_id)
        documents = [
            DocumentSummaryResponse(
                id=summary["id"],
                file_name=summary["file_name"],
                file_type=summary["file_type"],
                file_size=summary.get("file_size"),
                created_at=summary["created_at"],
                chunk_count=summary["chunk_count"],
            )
            for summary in summaries
        ]

        return DocumentListResponse(
            documents=documents,
            total_count=len(documents),
        )

    except Exception as e:
        logger.error(f"Error listing documents for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {e!s}"
        )


@router.get("/status", response_model=DocumentStatusResponse)
async def check_document_status(
    request: Request,
    tenant_id: UUID = PathParam(...),
    session: Session = Depends(get_db_session),
) -> DocumentStatusResponse:
    """Check if tenant has any documents uploaded for RAG."""

    # Validate tenant exists
    _validate_tenant(tenant_id, session)
    
    # Get RAG service
    rag_service = _get_rag_service(request)
    
    try:
        documents = await rag_service.list_documents(tenant_id)
        total_chunks = sum(doc["chunk_count"] for doc in documents)
        has_documents = bool(documents)
        
        return DocumentStatusResponse(
            has_documents=has_documents,
            document_count=len(documents),
            total_chunks=total_chunks,
        )
        
    except Exception as e:
        logger.error(f"Error checking document status for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check document status: {e!s}"
        )


@router.delete("/clear", response_model=DocumentDeleteResponse)
async def clear_documents(
    request: Request,
    tenant_id: UUID = PathParam(...),
    session: Session = Depends(get_db_session),
) -> DocumentDeleteResponse:
    """Clear all documents for a tenant.
    
    WARNING: This will delete all RAG documents and their embeddings for the tenant.
    This action cannot be undone.
    """

    # Validate tenant exists
    _validate_tenant(tenant_id, session)
    
    # Get RAG service
    rag_service = _get_rag_service(request)
    
    try:
        # Clear documents using vector store
        await rag_service.vector_store.clear_tenant_documents(tenant_id)
        
        logger.info(f"Cleared all documents for tenant {tenant_id}")
        return DocumentDeleteResponse(
            success=True,
            message=f"All documents cleared for tenant {tenant_id}"
        )
        
    except Exception as e:
        logger.error(f"Error clearing documents for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear documents: {e!s}"
        )


@router.post("/query", response_model=DocumentQueryResponse)
async def test_rag_query(
    request: Request,
    payload: DocumentQueryRequest,
    tenant_id: UUID = PathParam(...),
    session: Session = Depends(get_db_session),
) -> DocumentQueryResponse:
    """Execute a test query against the tenant's RAG documents."""

    _validate_tenant(tenant_id, session)
    rag_service = _get_rag_service(request)

    query_text = payload.query.strip()
    if not query_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query text is required"
        )

    try:
        result = await rag_service.query_structured(
            tenant_id=tenant_id,
            query=query_text,
            chat_history=None,
            business_context=None,
            thread_id=None,
        )

        query_chunks: list[DocumentQueryChunk] = []
        for chunk in result.get("chunks") or []:
            raw_id = chunk.get("id")
            if raw_id is None:
                continue
            try:
                chunk_uuid = UUID(str(raw_id))
            except (ValueError, TypeError):
                logger.debug("Skipping chunk with invalid UUID: %s", raw_id)
                continue

            query_chunks.append(
                DocumentQueryChunk(
                    id=chunk_uuid,
                    content=chunk.get("content", ""),
                    score=float(chunk.get("score", 0.0)),
                    category=chunk.get("category"),
                    keywords=chunk.get("keywords"),
                    possible_questions=chunk.get("possible_questions"),
                    metadata=chunk.get("metadata"),
                    document_name=chunk.get("document_name"),
                )
            )

        generated_answer = None
        if result.get("context") and result.get("success"):
            try:
                from langchain_openai import ChatOpenAI
                mini_llm = ChatOpenAI(model="gpt-5-mini", temperature=0.7)
                answer_prompt = f"""Você é um assistente de vendas especializado em iluminação LED industrial e esportiva.

Com base no contexto abaixo, responda a pergunta do usuário de forma clara, precisa e completa.

PERGUNTA: {query_text}

CONTEXTO:
{result.get("context")}

INSTRUÇÕES:
- Seja direto e objetivo
- Use números exatos do contexto
- Se houver múltiplos valores relevantes (ex: LED vs luminária), mencione ambos
- Inclua unidades de medida
- Use formato brasileiro (19.872 lm com ponto, não vírgula)
- Adicione observações úteis se aplicável

Responda em português brasileiro de forma profissional."""
                
                response = await mini_llm.ainvoke(answer_prompt)
                generated_answer = response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                logger.warning(f"Failed to generate answer preview: {e}")

        return DocumentQueryResponse(
            success=result.get("success", False),
            no_documents=result.get("no_documents", False),
            context=result.get("context"),
            judge_reasoning=result.get("judge_reasoning"),
            attempts=result.get("attempts", 0),
            sufficient=result.get("sufficient", False),
            chunks=query_chunks,
            error=result.get("error"),
            generated_answer=generated_answer,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing query for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute query: {e!s}"
        )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    request: Request,
    document_id: UUID = PathParam(...),
    tenant_id: UUID = PathParam(...),
    session: Session = Depends(get_db_session),
) -> DocumentDetailResponse:
    """Retrieve detailed information for a specific document."""

    _validate_tenant(tenant_id, session)
    rag_service = _get_rag_service(request)

    try:
        document = await rag_service.get_document(tenant_id, document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )

        chunk_models: list[DocumentChunkResponse] = []
        for chunk in document.get("chunks", []):
            raw_id = chunk.get("id")
            if raw_id is None:
                continue
            try:
                chunk_uuid = UUID(str(raw_id))
            except (ValueError, TypeError):
                logger.debug("Skipping chunk with invalid UUID: %s", raw_id)
                continue

            chunk_models.append(
                DocumentChunkResponse(
                    id=chunk_uuid,
                    chunk_index=chunk.get("chunk_index", 0),
                    content=chunk.get("content", ""),
                    category=chunk.get("category"),
                    keywords=chunk.get("keywords"),
                    possible_questions=chunk.get("possible_questions"),
                    metadata=chunk.get("metadata"),
                    created_at=chunk.get("created_at"),
                    updated_at=chunk.get("updated_at"),
                )
            )

        return DocumentDetailResponse(
            id=document["id"],
            file_name=document["file_name"],
            file_type=document["file_type"],
            file_size=document.get("file_size"),
            created_at=document["created_at"],
            updated_at=document.get("updated_at"),
            metadata=document.get("metadata"),
            chunk_count=document["chunk_count"],
            chunks=chunk_models,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving document {document_id} for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document: {e!s}"
        )


@router.patch("/{document_id}/metadata", response_model=UpdateMetadataResponse)
async def update_document_metadata(
    request: Request,
    payload: UpdateMetadataRequest,
    document_id: UUID = PathParam(...),
    tenant_id: UUID = PathParam(...),
    session: Session = Depends(get_db_session),
) -> UpdateMetadataResponse:
    """Update metadata for a specific document."""

    _validate_tenant(tenant_id, session)
    rag_service = _get_rag_service(request)

    try:
        success = await rag_service.update_document_metadata(
            tenant_id, document_id, payload.metadata
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )

        return UpdateMetadataResponse(
            success=True,
            message="Document metadata updated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating metadata for document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update document metadata: {e!s}"
        )


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    request: Request,
    document_id: UUID = PathParam(...),
    tenant_id: UUID = PathParam(...),
    session: Session = Depends(get_db_session),
) -> DocumentDeleteResponse:
    """Delete a single document and its chunks."""

    _validate_tenant(tenant_id, session)
    rag_service = _get_rag_service(request)

    try:
        deleted = await rag_service.delete_document(tenant_id, document_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )

        logger.info("Deleted document %s for tenant %s", document_id, tenant_id)
        return DocumentDeleteResponse(
            success=True,
            message=f"Document {document_id} deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {document_id} for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {e!s}"
        )
