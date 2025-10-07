"""Main RAG service orchestrating document processing and retrieval.

This service provides the high-level interface for the RAG system,
coordinating document parsing, chunking, embedding, and retrieval.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Literal, Optional, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langchain_core.documents import Document

from app.db.models import TenantProjectConfig
from app.services.rag.chunking import ChunkingService, DocumentChunkData
from app.services.rag.document_parser import DocumentParserService, DocumentType
from app.services.rag.embedding import EmbeddingService
from app.services.rag.judge import ChunkContext, JudgeService
from app.services.rag.vector_store import ChunkResult, VectorStoreRepository

logger = logging.getLogger(__name__)


class RAGState(TypedDict):
    """State for the RAG retrieval graph."""
    query: str
    attempts: int
    chunks: List[ChunkResult]
    sufficient: bool
    context: Optional[str]
    judge_reasoning: Optional[str]
    chat_history: Optional[List[Dict]]
    business_context: Optional[Dict]
    tenant_id: UUID
    thread_id: Optional[UUID]


class RAGService:
    """Main service orchestrating the RAG system.
    
    This service provides a clean interface for:
    - Saving documents with intelligent chunking
    - Querying documents with iterative retrieval
    - Managing tenant document collections
    """
    
    def __init__(
        self,
        openai_api_key: str,
        vector_db_url: str,
        max_retrieval_attempts: int = 3
    ):
        """Initialize the RAG service.
        
        Args:
            openai_api_key: OpenAI API key for GPT models
            vector_db_url: PostgreSQL URL with pgvector
            max_retrieval_attempts: Maximum retrieval attempts
        """
        # Initialize sub-services
        self.document_parser = DocumentParserService()
        self.chunking_service = ChunkingService(openai_api_key)
        self.embedding_service = EmbeddingService(openai_api_key)
        self.judge_service = JudgeService(openai_api_key)
        self.vector_store = VectorStoreRepository(vector_db_url)
        
        self.max_attempts = max_retrieval_attempts
        
        # Build the retrieval graph
        self.retrieval_app = self._build_retrieval_graph()
        
        # Initialize vector store on startup
        asyncio.create_task(self._initialize())
    
    async def _initialize(self):
        """Initialize the vector store."""
        try:
            await self.vector_store.initialize()
            logger.info("RAG service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RAG service: {e}")
    
    async def has_documents(self, tenant_id: UUID) -> bool:
        """Check if tenant has any documents stored.
        
        Args:
            tenant_id: Tenant UUID
            
        Returns:
            True if tenant has documents
        """
        return await self.vector_store.has_documents(tenant_id)
    
    async def save_document(
        self,
        tenant_id: UUID,
        file_path: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, any]:
        """Save a document with intelligent chunking and embedding.
        
        Args:
            tenant_id: Tenant UUID
            file_path: Path to document file
            metadata: Optional document metadata
            
        Returns:
            Dictionary with save results
        """
        logger.info(f"Saving document for tenant {tenant_id}: {file_path}")
        
        try:
            # 1. Parse document
            parsed_doc = self.document_parser.parse_document(file_path)
            logger.info(f"Parsed document: {parsed_doc.char_count} chars, {parsed_doc.word_count} words")
            
            # 2. Store raw document
            document_id = await self.vector_store.store_document(
                tenant_id=tenant_id,
                file_name=parsed_doc.file_name,
                file_type=parsed_doc.file_type.value,
                raw_content=parsed_doc.content,
                parsed_content=parsed_doc.content,
                metadata={**parsed_doc.metadata, **(metadata or {})}
            )
            
            # 3. Intelligent chunking with GPT-5
            chunks = await self.chunking_service.chunk_document(
                document_content=parsed_doc.content,
                document_metadata=parsed_doc.metadata
            )
            
            # Optimize chunks if needed
            chunks = self.chunking_service.optimize_chunks(chunks)
            logger.info(f"Created {len(chunks)} semantic chunks")
            
            # 4. Generate embeddings for chunks
            chunk_texts = [chunk.content for chunk in chunks]
            embeddings = await self.embedding_service.embed_texts(chunk_texts)
            
            # 5. Prepare chunks for storage
            chunks_data = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunks_data.append({
                    'content': chunk.content,
                    'embedding': embedding,
                    'metadata': chunk.metadata.dict() if hasattr(chunk.metadata, 'dict') else chunk.metadata,
                    'category': chunk.metadata.category,
                    'keywords': chunk.metadata.keywords,
                    'possible_questions': chunk.metadata.possible_questions
                })
            
            # 6. Store chunks with embeddings
            chunk_ids = await self.vector_store.store_chunks(
                document_id=document_id,
                tenant_id=tenant_id,
                chunks=chunks_data
            )
            
            # 7. Store chunk relationships
            relationships = []
            chunk_id_map = {chunk.chunk_id: chunk_ids[i] for i, chunk in enumerate(chunks)}
            
            for chunk, chunk_id in zip(chunks, chunk_ids):
                for related in chunk.related_chunks:
                    if related['id'] in chunk_id_map:
                        relationships.append((
                            chunk_id,
                            chunk_id_map[related['id']],
                            'related',
                            related['reason']
                        ))
            
            if relationships:
                await self.vector_store.store_chunk_relationships(relationships)
                logger.info(f"Stored {len(relationships)} chunk relationships")
            
            return {
                'success': True,
                'document_id': str(document_id),
                'file_name': parsed_doc.file_name,
                'chunks_created': len(chunks),
                'relationships_created': len(relationships),
                'total_words': parsed_doc.word_count
            }
            
        except Exception as e:
            logger.error(f"Error saving document: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def query(
        self,
        tenant_id: UUID,
        query: str,
        chat_history: Optional[List[Dict]] = None,
        business_context: Optional[Dict] = None,
        thread_id: Optional[UUID] = None
    ) -> str:
        """Query the RAG system for relevant context.
        
        Args:
            tenant_id: Tenant UUID
            query: User's query
            chat_history: Previous conversation messages
            business_context: Tenant business configuration
            thread_id: Optional chat thread ID for tracking
            
        Returns:
            Context string for the tool caller LLM or error message
        """
        logger.info(f"RAG query for tenant {tenant_id}: {query[:100]}")
        
        # Check if tenant has documents
        if not await self.has_documents(tenant_id):
            return "No documents available. The tenant hasn't uploaded any context documents yet."
        
        # Run the retrieval graph
        initial_state: RAGState = {
            'query': query,
            'attempts': 0,
            'chunks': [],
            'sufficient': False,
            'context': None,
            'judge_reasoning': None,
            'chat_history': chat_history,
            'business_context': business_context,
            'tenant_id': tenant_id,
            'thread_id': thread_id
        }
        
        try:
            result = await self.retrieval_app.ainvoke(initial_state)
            
            # Save retrieval session for analytics
            if result.get('chunks'):
                chunks_data = [
                    {'id': str(c.chunk_id), 'score': c.score} 
                    for c in result['chunks'][:20]
                ]
                
                # Save retrieval session for analytics (skip on error to prevent hanging)
                try:
                    # Generate query embedding for analytics
                    query_embedding = await self.embedding_service.embed_text(query)
                    
                    await self.vector_store.save_retrieval_session(
                        tenant_id=tenant_id,
                        query=query,
                        query_embedding=query_embedding,
                        retrieved_chunks=chunks_data,
                        final_context=result.get('context', ''),
                        attempts=result.get('attempts', 0),
                        sufficient=result.get('sufficient', False),
                        judge_reasoning=result.get('judge_reasoning', ''),
                        thread_id=thread_id
                    )
                except Exception as e:
                    # Skip saving session to prevent hanging
                    logger.debug(f"Skipped saving retrieval session: {e}")
            
            # Return context or empty when insufficient; never emit user-facing text here
            if result.get('sufficient') and result.get('context'):
                return result['context']
            else:
                # Insufficient context; upstream caller should decide how to respond
                return ""
                
        except Exception as e:
            logger.error(f"Error in RAG query: {e}")
            return f"Error retrieving context: {str(e)}. Please try rephrasing the question."
    
    def _build_retrieval_graph(self) -> StateGraph:
        """Build the LangGraph retrieval loop.
        
        Returns:
            Compiled StateGraph for retrieval
        """
        graph = StateGraph(RAGState)
        
        # Add nodes
        graph.add_node("retrieve", self._retrieve_node)
        graph.add_node("analyze", self._analyze_node)
        graph.add_node("finalize", self._finalize_node)
        
        # Add edges
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "analyze")
        
        # Conditional routing after analysis
        graph.add_conditional_edges(
            "analyze",
            self._routing_logic,
            {
                "retry": "retrieve",
                "done": "finalize",
                "fail": "finalize"
            }
        )
        
        graph.add_edge("finalize", END)
        
        # Set recursion limit to prevent infinite loops
        config = {"recursion_limit": 10}
        return graph.compile(checkpointer=None)
    
    async def _retrieve_node(self, state: RAGState) -> RAGState:
        """Retrieve chunks from vector store.
        
        Args:
            state: Current RAG state
            
        Returns:
            Updated state with retrieved chunks
        """
        attempts = state.get('attempts', 0)
        
        # Widen search on retries
        base_k = 6
        k = base_k + attempts * 4
        
        # Lower threshold on retries
        base_threshold = 0.5  # Start with lower threshold for better recall
        threshold = max(0.3, base_threshold - attempts * 0.1)
        
        logger.info(f"Retrieval attempt {attempts + 1}: k={k}, threshold={threshold}")
        
        # Generate query embedding
        query_embedding = await self.embedding_service.embed_text(state['query'])
        
        # Search for similar chunks
        chunks = await self.vector_store.search_similar_chunks(
            tenant_id=state['tenant_id'],
            query_embedding=query_embedding,
            limit=k,
            similarity_threshold=threshold
        )
        
        # If we have chunks, also get related chunks
        if chunks and attempts > 0:
            chunk_ids = [chunk.chunk_id for chunk in chunks[:5]]
            related_chunks = await self.vector_store.get_related_chunks(
                chunk_ids=chunk_ids,
                relationship_types=['related', 'extends']
            )
            
            # Add related chunks if not already present
            existing_ids = {c.chunk_id for c in chunks}
            for related in related_chunks:
                if related.chunk_id not in existing_ids:
                    chunks.append(related)
        
        state['chunks'] = chunks
        # Increment attempts after retrieval (not before)
        state['attempts'] = attempts + 1
        
        return state
    
    async def _analyze_node(self, state: RAGState) -> RAGState:
        """Analyze retrieved chunks with judge.
        
        Args:
            state: Current RAG state
            
        Returns:
            Updated state with judgment
        """
        chunks = state.get('chunks', [])
        
        if not chunks:
            state['sufficient'] = False
            state['judge_reasoning'] = "No chunks retrieved"
            return state
        
        # Convert to ChunkContext for judge
        chunk_contexts = [
            ChunkContext(
                chunk_id=str(chunk.chunk_id),
                content=chunk.content,
                score=chunk.score,
                category=chunk.category,
                possible_questions=chunk.possible_questions
            )
            for chunk in chunks
        ]
        
        # Judge chunks
        judgment = await self.judge_service.judge_chunks(
            query=state['query'],
            chunks=chunk_contexts,
            chat_history=state.get('chat_history'),
            business_context=state.get('business_context')
        )
        
        state['sufficient'] = judgment.sufficient
        state['judge_reasoning'] = judgment.reasoning
        
        # If sufficient, prepare context
        if judgment.sufficient:
            # Build comprehensive context with all relevant information
            context_parts = [
                f"## Contexto Relevante para: {state['query']}\n",
                f"### Avaliação: {judgment.reasoning}\n"
            ]
            
            # Add chunks with metadata
            for i, chunk in enumerate(chunks[:10], 1):
                context_parts.append(f"\n### Documento {i}")
                if chunk.document_name:
                    context_parts.append(f"**Fonte:** {chunk.document_name}")
                if chunk.category:
                    context_parts.append(f"**Categoria:** {chunk.category}")
                context_parts.append(f"**Relevância:** {chunk.score:.2%}")
                context_parts.append(f"\n{chunk.content}\n")
            
            # Add any missing information notes
            if judgment.missing_info:
                context_parts.append("\n### Informações Adicionais Necessárias:")
                for info in judgment.missing_info:
                    context_parts.append(f"- {info}")
            
            state['context'] = "\n".join(context_parts)
        
        return state
    
    def _routing_logic(self, state: RAGState) -> Literal["retry", "done", "fail"]:
        """Determine next step after analysis.
        
        Args:
            state: Current RAG state
            
        Returns:
            Next node to execute
        """
        # If sufficient, we're done
        if state.get('sufficient'):
            return "done"
        
        # If not sufficient and we have attempts left, retry
        attempts = state.get('attempts', 0)
        if attempts < self.max_attempts - 1:
            # Don't modify state here - let retrieve_node handle it
            return "retry"
        
        # Out of attempts
        return "fail"
    
    async def _finalize_node(self, state: RAGState) -> RAGState:
        """Finalize the retrieval process.
        
        Args:
            state: Current RAG state
            
        Returns:
            Final state
        """
        if state.get('sufficient') and state.get('context'):
            logger.info(f"RAG retrieval successful after {state['attempts'] + 1} attempts")
            return state
        
        # Not sufficient - provide clear message
        state['context'] = None
        logger.warning(f"RAG retrieval failed after {state['attempts'] + 1} attempts: {state.get('judge_reasoning', 'Unknown reason')}")
        
        return state
    
    async def delete_document(self, document_id: UUID):
        """Delete a document and all its chunks.
        
        Args:
            document_id: Document UUID to delete
        """
        await self.vector_store.delete_document(document_id)
    
    async def get_tenant_stats(self, tenant_id: UUID) -> Dict:
        """Get statistics for a tenant's documents.
        
        Args:
            tenant_id: Tenant UUID
            
        Returns:
            Dictionary with statistics
        """
        has_docs = await self.has_documents(tenant_id)
        chunk_count = await self.vector_store.get_tenant_chunks_count(tenant_id) if has_docs else 0
        
        return {
            'has_documents': has_docs,
            'total_chunks': chunk_count,
            'rag_enabled': has_docs and chunk_count > 0
        }
    
    async def close(self):
        """Clean up resources."""
        await self.vector_store.close()
