"""Judge service for evaluating chunk relevance using GPT-5-mini.

This service uses GPT-5-mini to assess whether retrieved chunks
contain sufficient information to answer user queries.
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class ChunkContext:
    """Context for a single chunk."""
    chunk_id: str
    content: str
    score: float
    category: Optional[str] = None
    keywords: Optional[str] = None
    possible_questions: Optional[List[str]] = None


class JudgmentResult(BaseModel):
    """Result of judging chunk relevance."""
    sufficient: bool = Field(description="Whether chunks are sufficient")
    confidence: float = Field(description="Confidence score 0-1")
    reasoning: str = Field(description="Explanation of judgment")
    missing_info: List[str] = Field(default_factory=list, description="What information is missing")
    relevant_chunks: List[str] = Field(default_factory=list, description="IDs of relevant chunks")
    suggestions: List[str] = Field(default_factory=list, description="Suggestions for better retrieval")


class JudgeService:
    """Service for judging chunk relevance using GPT-5-mini."""
    
    def __init__(self, openai_api_key: str):
        """Initialize the judge service.
        
        Args:
            openai_api_key: OpenAI API key
        """
        # GPT-5-mini for fast, efficient judgment
        self.judge_model = ChatOpenAI(
            model="gpt-5-mini",
            temperature=0,
            api_key=openai_api_key,
        )
        
        self.judge_prompt = self._create_judge_prompt()
    
    def _create_judge_prompt(self) -> str:
        """Create the prompt for judging chunk relevance."""
        return """You are a strict relevance judge for a RAG (Retrieval-Augmented Generation) system.
Your task: Determine if retrieved chunks contain sufficient information to answer the user's query.

CONTEXT:
- User Query: {query}
- Business Context: {business_context}
- Chat History: {chat_history}
- Retrieved Chunks: {chunks}

EVALUATION CRITERIA:

Mark as SUFFICIENT when:
- Direct answer to the query exists
- All key facts requested are present
- Technical specifications match the query
- Product information is complete

Mark as INSUFFICIENT when:
- Only partial information available
- Answer is vague or indirect
- Missing critical technical specs or prices
- Chunks discuss related but different topics
- Information contradicts chat history

OUTPUT FORMAT (JSON):
{{
  "sufficient": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Clear explanation of judgment",
  "missing_info": ["what's missing"],
  "relevant_chunks": ["chunk_001", "chunk_002"],
  "suggestions": ["search for X", "need more on Y"]
}}

BE STRICT: It's better to fetch more chunks than give incomplete answers.
IMPORTANT: Include ALL relevant technical details, prices, and specifications in your reasoning so the tool caller LLM has maximum context."""
    
    async def judge_chunks(
        self,
        query: str,
        chunks: List[ChunkContext],
        chat_history: Optional[List[Dict]] = None,
        business_context: Optional[Dict] = None
    ) -> JudgmentResult:
        """Judge if chunks are sufficient to answer the query.
        
        Args:
            query: User's query
            chunks: Retrieved chunks with context
            chat_history: Previous conversation
            business_context: Business/tenant context
            
        Returns:
            JudgmentResult with assessment
        """
        logger.info(f"Judging {len(chunks)} chunks for query: {query}")
        
        # Format chunks for prompt
        chunks_str = self._format_chunks(chunks)
        
        # Format chat history
        history_str = self._format_chat_history(chat_history or [])
        
        # Format business context
        context_str = json.dumps(business_context or {}, ensure_ascii=False)
        
        # Create prompt
        prompt = self.judge_prompt.format(
            query=query,
            chunks=chunks_str,
            chat_history=history_str,
            business_context=context_str
        )
        
        try:
            # Get judgment from GPT-5-mini
            response = await self.judge_model.ainvoke(prompt)
            
            # Handle GPT-5-mini's response format
            if isinstance(response.content, list):
                # GPT-5 returns list format
                content_text = ""
                for item in response.content:
                    if isinstance(item, dict) and 'text' in item:
                        content_text += item['text']
                    else:
                        content_text += str(item)
            else:
                # String format
                content_text = response.content
            
            # Parse response
            result = self._parse_judgment(content_text)
            
            logger.info(f"Judgment: sufficient={result.sufficient}, confidence={result.confidence}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in judge service: {e}")
            # Return conservative judgment on error
            return JudgmentResult(
                sufficient=False,
                confidence=0.0,
                reasoning=f"Error during judgment: {str(e)}",
                missing_info=["Unable to assess due to error"],
                relevant_chunks=[],
                suggestions=["Retry with different parameters"]
            )
    
    def _format_chunks(self, chunks: List[ChunkContext]) -> str:
        """Format chunks for the prompt.
        
        Args:
            chunks: List of chunk contexts
            
        Returns:
            Formatted string representation
        """
        formatted = []
        
        for i, chunk in enumerate(chunks, 1):
            chunk_str = f"Chunk {i} (ID: {chunk.chunk_id}, Score: {chunk.score:.3f})"
            
            if chunk.category:
                chunk_str += f" [Category: {chunk.category}]"
            
            chunk_str += f":\n{chunk.content}"
            
            if chunk.possible_questions:
                chunk_str += f"\nCan answer: {', '.join(chunk.possible_questions[:3])}"
            
            formatted.append(chunk_str)
        
        return "\n\n".join(formatted)
    
    def _format_chat_history(self, chat_history: List[Dict]) -> str:
        """Format chat history for context.
        
        Args:
            chat_history: List of chat messages
            
        Returns:
            Formatted chat history
        """
        if not chat_history:
            return "No previous conversation"
        
        formatted = []
        for msg in chat_history[-5:]:  # Last 5 messages for context
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            formatted.append(f"{role}: {content}")
        
        return "\n".join(formatted)
    
    def _parse_judgment(self, response: str) -> JudgmentResult:
        """Parse the judge's response.
        
        Args:
            response: Model's response text
            
        Returns:
            Parsed JudgmentResult
        """
        try:
            # Try to extract JSON from response
            import re
            # Look for JSON object - handle potential formatting issues
            response_clean = response.strip()
            
            # Try to find JSON block
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_clean, re.DOTALL)
            
            if json_match:
                json_str = json_match.group()
                # Clean up common issues
                json_str = json_str.replace('\n', ' ').replace('\r', '')
                data = json.loads(json_str)
                
                return JudgmentResult(
                    sufficient=bool(data.get('sufficient', False)),
                    confidence=float(data.get('confidence', 0.5)),
                    reasoning=str(data.get('reasoning', 'No reasoning provided')),
                    missing_info=data.get('missing_info', []) if isinstance(data.get('missing_info'), list) else [],
                    relevant_chunks=data.get('relevant_chunks', []) if isinstance(data.get('relevant_chunks'), list) else [],
                    suggestions=data.get('suggestions', []) if isinstance(data.get('suggestions'), list) else []
                )
            else:
                # Fallback parsing from text
                sufficient = 'sufficient' in response.lower() and 'insufficient' not in response.lower()
                return JudgmentResult(
                    sufficient=sufficient,
                    confidence=0.5,
                    reasoning=response[:500],  # First 500 chars as reasoning
                    missing_info=[],
                    relevant_chunks=[],
                    suggestions=[]
                )
                
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse judge response as JSON: {e}")
            
            # Fallback: Simple text analysis
            sufficient = 'sufficient' in response.lower() and 'insufficient' not in response.lower()
            
            return JudgmentResult(
                sufficient=sufficient,
                confidence=0.5,
                reasoning=response[:500],
                missing_info=[],
                relevant_chunks=[],
                suggestions=[]
            )
