# RAG Scripts Guide

## 📋 Quick Reference

All scripts use test tenant: `068b37cd-c090-710d-b0b6-5ca37c2887ff`

## 🔧 Main Scripts

### 1. **reset_and_upload_rag.py** - Reset & Upload
```bash
python reset_and_upload_rag.py
```
- Clears entire vector DB
- Uploads PDFs to test tenant
- Shows verification results
- **Use this for clean slate testing**

### 2. **test_rag_integration.py** - Full Test Suite
```bash
# Upload documents
python test_rag_integration.py --upload

# Test queries
python test_rag_integration.py --query

# Test flow integration
python test_rag_integration.py --flow

# Interactive mode
python test_rag_integration.py --interactive

# All tests
python test_rag_integration.py --all
```

### 3. **simple_rag_cli.py** - Quick Interactive Queries
```bash
python simple_rag_cli.py
```
- Simple chat interface
- Ask questions about uploaded documents
- Type 'exit' to quit

### 4. **list_documents.py** - View Database Contents
```bash
python list_documents.py
```
- Shows all documents in vector DB
- Shows chunks per document
- No external dependencies

### 5. **rag_query.py** - Single Query Tool
```bash
python rag_query.py "Qual a potência do HB-240?"
```
- Run a single query from command line

## 📁 Documents Location

PDFs are in: `playground/documents/pdfs/`

Current documents:
- `catalogo_luminarias_desordenado.pdf` (6 chunks)
- `catalogo_de_produtos_led.pdf` (8 chunks)

## 🧠 Core RAG Services

The actual RAG logic is in the service layer, NOT in these scripts:

- **`app/services/rag/rag_service.py`** - Main orchestrator
- **`app/services/rag/chunking.py`** - Intelligent chunking (GPT-5)
- **`app/services/rag/embedding.py`** - Text embeddings
- **`app/services/rag/judge.py`** - Retrieval judge
- **`app/services/rag/vector_store.py`** - Database operations
- **`app/services/rag/document_parser.py`** - PDF/text parsing

## 🎯 Workflow

1. **Upload documents**: `python reset_and_upload_rag.py`
2. **Verify**: `python list_documents.py`
3. **Test queries**: `python simple_rag_cli.py`
4. **Full integration test**: `python test_rag_integration.py --all`

## 🔒 Tenant Separation

All scripts use the correct test tenant ID. The RAG system enforces tenant separation at the database level - documents from one tenant are NEVER retrieved for another tenant's queries.

