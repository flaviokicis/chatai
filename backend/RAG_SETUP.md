# RAG System Setup Guide

## Overview

The RAG (Retrieval-Augmented Generation) system is now integrated into the chatbot platform, allowing tenants to upload documents that will be used to enhance AI responses with relevant context.

## Environment Variables

Add these environment variables to your `.env` file:

```bash
# Main PostgreSQL database (existing)
DATABASE_URL=postgresql://user:password@localhost:5432/chatai

# Separate PostgreSQL database with pgvector extension for RAG
PG_VECTOR_DATABASE_URL=postgresql://user:password@localhost:5432/chatai_vectors

# OpenAI API key (required for embeddings and RAG judge)
OPENAI_API_KEY=sk-your-openai-api-key
```

## Database Setup

### 1. Create the Vector Database

```sql
-- Create a separate database for vector storage
CREATE DATABASE chatai_vectors;

-- Connect to the new database
\c chatai_vectors;

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. Run Database Migrations

The RAG system uses the existing SQLAlchemy models that will be created automatically on startup. The tables include:

- `tenant_documents` - Stores uploaded documents
- `document_chunks` - Stores document chunks with embeddings
- `chunk_relationships` - Stores relationships between chunks
- `retrieval_sessions` - Tracks retrieval sessions for monitoring

### 3. Initialize Vector Database

Run the initialization script to set up tables and indexes:

```bash
source .venv/bin/activate
cd backend
python init_vector_db.py
```

## API Endpoints

### Upload Document

```bash
POST /api/tenants/{tenant_id}/documents/upload

# Example with curl
curl -X POST \
  "http://localhost:8000/api/tenants/{tenant_id}/documents/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf"
```

Supported file types:
- PDF (.pdf)
- Text files (.txt, .md)
- JSON files (.json)

Maximum file size: 10MB

### Check Document Status

```bash
GET /api/tenants/{tenant_id}/documents/status

# Response
{
  "has_documents": true,
  "document_count": 5
}
```

### Clear All Documents

```bash
DELETE /api/tenants/{tenant_id}/documents/clear

# Response
{
  "message": "All documents cleared for tenant {tenant_id}"
}
```

## How RAG Works

### 1. Document Processing Pipeline

When a document is uploaded:
1. **Parsing**: Extract text content from the document
2. **Intelligent Chunking**: Split into semantic chunks using GPT-4
3. **Embedding**: Generate embeddings using text-embedding-3-large
4. **Storage**: Store chunks and embeddings in pgvector

### 2. Query Processing

When a user sends a message:
1. **RAG Query**: FlowTurnRunner queries RAG system before responding
2. **Iterative Retrieval**: Up to 3 attempts to find relevant chunks
3. **Judge Evaluation**: GPT-4 evaluates if chunks are sufficient
4. **Context Integration**: Relevant documents added to FlowContext
5. **Response Generation**: LLM uses RAG context to generate response

### 3. Integration Points

- **FlowContext**: Added `rag_documents` and `rag_query_performed` fields
- **AppContext**: Added `rag_service` for application-wide access
- **FlowTurnRunner**: Queries RAG before calling responder
- **FlowProcessor**: Passes RAGService to FlowTurnRunner

## Testing RAG

### 1. Validate RAG System

```bash
python validate_rag_system.py
```

### 2. Test Document Upload

```python
import aiohttp
import asyncio

async def test_upload():
    tenant_id = "your-tenant-uuid"
    file_path = "test_document.pdf"
    
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename='test.pdf')
            
            async with session.post(
                f"http://localhost:8000/api/tenants/{tenant_id}/documents/upload",
                data=data
            ) as resp:
                result = await resp.json()
                print(result)

asyncio.run(test_upload())
```

### 3. Test RAG Query

Once documents are uploaded, send messages through the flow chat endpoint:

```bash
POST /api/flows/{flow_id}/chat/send
{
  "content": "What does the document say about pricing?"
}
```

The system will automatically query RAG and include relevant context in the response.

## Monitoring

### Check Logs

RAG operations are logged with info level:
- "RAG service initialized with pgvector database"
- "Querying RAG for relevant context"
- "RAG context retrieved and added to flow context"

### Database Queries

Check chunk count for a tenant:

```sql
SELECT COUNT(*) FROM document_chunks WHERE tenant_id = 'tenant-uuid';
```

Check retrieval sessions:

```sql
SELECT * FROM retrieval_sessions 
WHERE tenant_id = 'tenant-uuid' 
ORDER BY created_at DESC LIMIT 10;
```

## Troubleshooting

### RAG Service Not Initialized

If you see "RAG service not initialized" in logs:
1. Check `PG_VECTOR_DATABASE_URL` is set correctly
2. Check `OPENAI_API_KEY` is valid
3. Ensure pgvector database is accessible
4. Check for connection errors in logs

### No RAG Context in Responses

If RAG context isn't being used:
1. Verify documents are uploaded for the tenant
2. Check `has_documents` endpoint returns true
3. Look for "Querying RAG" in logs
4. Verify tenant_id is correctly passed in FlowContext

### Document Upload Failures

If documents fail to upload:
1. Check file size (< 10MB)
2. Verify file type is supported
3. Check OpenAI API key for embeddings
4. Look for errors in chunking service logs

## Performance Considerations

1. **Embedding Dimensions**: Using 2000 dimensions (pgvector limit) for text-embedding-3-large
2. **Chunk Size**: Optimized for ~300-500 tokens per chunk
3. **Retrieval Attempts**: Maximum 3 attempts with expanding search
4. **Similarity Threshold**: Set to 0.7 for relevance filtering

## Security

1. **Tenant Isolation**: Each tenant's documents are strictly isolated
2. **File Validation**: Only allowed file types are processed
3. **Size Limits**: 10MB maximum file size
4. **SQL Injection Prevention**: Using parameterized queries throughout
