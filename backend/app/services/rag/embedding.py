"""Embedding service using OpenAI's text-embedding-3-large model.

This service handles the generation of embeddings for document chunks
and queries for vector similarity search. Uses text-embedding-3-large
with reduced dimensions for pgvector compatibility while maintaining
superior quality compared to smaller models.
"""

import logging

import numpy as np
from langchain_openai import OpenAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings using OpenAI's text-embedding-3-large.
    
    This model produces reduced 2000-dimensional embeddings from the full 3072
    dimensions, maximizing quality while staying within pgvector's 2000 
    dimension index limit.
    """
    
    def __init__(self, openai_api_key: str, dimensions: int = 2000):
        """Initialize the embedding service.
        
        Args:
            openai_api_key: OpenAI API key
            dimensions: Output dimensions (max 3072, pgvector limit is 2000)
        """
        # Ensure dimensions are within pgvector limits
        if dimensions > 2000:
            logger.warning(f"Dimensions {dimensions} exceeds pgvector limit, using 2000")
            dimensions = 2000
            
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",
            openai_api_key=openai_api_key,
            dimensions=dimensions  # Reduced dimensions for pgvector compatibility
        )
        self.dimension = dimensions
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        try:
            # Use async method for single text
            embedding = await self.embeddings.aembed_query(text)
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        try:
            # Use async method for batch processing
            embeddings = await self.embeddings.aembed_documents(texts)
            return embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings for {len(texts)} texts: {e}")
            raise
    
    def compute_similarity(
        self,
        query_embedding: list[float],
        document_embeddings: list[list[float]]
    ) -> list[float]:
        """Compute cosine similarity between query and documents.
        
        Args:
            query_embedding: Query vector
            document_embeddings: List of document vectors
            
        Returns:
            List of similarity scores (0-1)
        """
        query_vec = np.array(query_embedding)
        doc_vecs = np.array(document_embeddings)
        
        # Normalize vectors
        query_norm = query_vec / np.linalg.norm(query_vec)
        doc_norms = doc_vecs / np.linalg.norm(doc_vecs, axis=1)[:, np.newaxis]
        
        # Compute cosine similarity
        similarities = np.dot(doc_norms, query_norm)
        
        # Convert to Python list and ensure range [0, 1]
        return ((similarities + 1) / 2).tolist()
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this service.
        
        Returns:
            Embedding dimension (default 2000 for text-embedding-3-large)
        """
        return self.dimension
    
    async def embed_with_metadata(
        self,
        text: str,
        metadata: dict | None = None
    ) -> dict:
        """Generate embedding with associated metadata.
        
        Args:
            text: Text to embed
            metadata: Optional metadata to attach
            
        Returns:
            Dictionary with embedding and metadata
        """
        embedding = await self.embed_text(text)
        return {
            "embedding": embedding,
            "text": text,
            "metadata": metadata or {},
            "dimension": self.dimension
        }
    
    def validate_embedding(self, embedding: list[float]) -> bool:
        """Validate that an embedding has the correct dimension.
        
        Args:
            embedding: Embedding vector to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not embedding:
            return False
        if len(embedding) != self.dimension:
            logger.warning(f"Invalid embedding dimension: {len(embedding)} (expected {self.dimension})")
            return False
        return True
