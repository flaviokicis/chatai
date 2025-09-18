#!/usr/bin/env python3
"""Test the judge service directly."""

import asyncio
import logging
from dotenv import load_dotenv

from app.services.rag.judge import JudgeService, ChunkContext
from app.settings import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def test_judge():
    settings = get_settings()
    
    # Initialize judge
    judge = JudgeService(settings.openai_api_key)
    
    # Create test chunks
    chunks = [
        ChunkContext(
            chunk_id="test_001",
            content="HIGHBAY LED 200W - Potência: 200 watts (consumo real ~210W) - Lumens: 28000lm - Ângulo: 90° ou 120° - IP65 - Garantia: 5 anos - Preço: R$ 890,00",
            score=0.85,
            category="product_specs",
            possible_questions=["Qual a potência da HIGHBAY?", "Quanto custa a HIGHBAY 200W?"]
        ),
        ChunkContext(
            chunk_id="test_002", 
            content="UFO 300W - Potência: 300 watts - Lumens: 42000lm - Para galpões acima de 8m",
            score=0.65,
            category="product_specs"
        )
    ]
    
    # Test query
    query = "Qual a potência da luminária HIGHBAY LED 200W?"
    
    logger.info(f"Testing judge with query: {query}")
    logger.info(f"Number of chunks: {len(chunks)}")
    
    try:
        judgment = await judge.judge_chunks(
            query=query,
            chunks=chunks,
            chat_history=[],
            business_context={
                "project_description": "Empresa de iluminação LED"
            }
        )
        
        logger.info(f"Judgment result:")
        logger.info(f"  Sufficient: {judgment.sufficient}")
        logger.info(f"  Confidence: {judgment.confidence}")
        logger.info(f"  Reasoning: {judgment.reasoning}")
        logger.info(f"  Missing info: {judgment.missing_info}")
        logger.info(f"  Relevant chunks: {judgment.relevant_chunks}")
        
    except Exception as e:
        logger.error(f"Error in judge test: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_judge())
