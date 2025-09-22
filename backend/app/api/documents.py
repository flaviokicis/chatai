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
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Path as PathParam, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.app_context import get_app_context
from app.db.models import TenantProjectConfig
from app.db.session import get_db_session
from app.services.rag.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tenants/{tenant_id}/documents", tags=["documents"])


class DocumentUploadResponse(BaseModel):
    """Response model for document upload."""
    
    success: bool
    message: str
    document_id: str | None = None
    chunks_created: int = 0
    total_words: int = 0
    error: str | None = None


class DocumentListResponse(BaseModel):
    """Response model for listing documents."""
    
    documents: list[dict[str, Any]]
    total_count: int


class DocumentStatusResponse(BaseModel):
    """Response model for document status check."""
    
    has_documents: bool
    document_count: int = 0


def _get_rag_service(request: Request) -> RAGService:
    """Get RAG service from app context or raise error."""
    ctx = get_app_context(request.app)
    if not ctx.rag_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service is not configured. Please set PG_VECTOR_DATABASE_URL and OPENAI_API_KEY."
        )
    return ctx.rag_service


def _validate_tenant(tenant_id: UUID, session: Session) -> TenantProjectConfig:
    """Validate that tenant exists and return it."""
    tenant = session.query(TenantProjectConfig).filter_by(id=tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
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
    
    allowed_extensions = {'.pdf', '.txt', '.md', '.json'}
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
            detail=f"File too large. Maximum size is 10MB."
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
            "business_name": tenant.business_name,
        }
        
        result = await rag_service.save_document(
            tenant_id=tenant_id,
            file_path=tmp_path,
            metadata=metadata
        )
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        if result.get('success'):
            return DocumentUploadResponse(
                success=True,
                message=f"Document '{file.filename}' uploaded successfully",
                document_id=result.get('document_id'),
                chunks_created=result.get('chunks_created', 0),
                total_words=result.get('total_words', 0)
            )
        else:
            return DocumentUploadResponse(
                success=False,
                message="Failed to process document",
                error=result.get('error', 'Unknown error occurred')
            )
            
    except Exception as e:
        logger.error(f"Error uploading document for tenant {tenant_id}: {e}")
        # Clean up temp file if it exists
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(e)}"
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
        has_documents = await rag_service.has_documents(tenant_id)
        
        # For now, we don't have a count method, so we'll just return boolean status
        return DocumentStatusResponse(
            has_documents=has_documents,
            document_count=1 if has_documents else 0  # Simplified for now
        )
        
    except Exception as e:
        logger.error(f"Error checking document status for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check document status: {str(e)}"
        )


@router.delete("/clear")
async def clear_documents(
    request: Request,
    tenant_id: UUID = PathParam(...),
    session: Session = Depends(get_db_session),
) -> dict[str, str]:
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
        return {"message": f"All documents cleared for tenant {tenant_id}"}
        
    except Exception as e:
        logger.error(f"Error clearing documents for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear documents: {str(e)}"
        )
