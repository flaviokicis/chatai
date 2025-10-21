"""Intelligent document chunking service using GPT-5.

This service uses GPT-5 with high reasoning to intelligently segment documents
into semantic chunks with rich metadata.
"""

import io
import logging
import xml.etree.ElementTree as ET

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ChunkMetadata(BaseModel):
    """Metadata for a document chunk."""
    about: str = Field(description="Brief description of what this chunk contains")
    category: str = Field(description="Category: product_specs, pricing, installation, warranty, etc")
    keywords: str = Field(description="Comma-separated keywords for hybrid search")
    possible_questions: list[str] = Field(description="Questions this chunk can answer")


class DocumentChunkData(BaseModel):
    """Represents a single document chunk with metadata."""
    chunk_id: str
    content: str
    metadata: ChunkMetadata
    related_chunks: list[dict[str, str]] = Field(default_factory=list)  # {id, reason}


class ChunkingService:
    """Service for intelligent document chunking using GPT-5.
    
    This service leverages GPT-5's high reasoning capabilities to create
    semantic chunks that preserve context and identify relationships.
    """
    
    def __init__(self, openai_api_key: str):
        """Initialize the chunking service.
        
        Args:
            openai_api_key: OpenAI API key for GPT-5 access
        """
        # GPT-5 with high reasoning for intelligent chunking
        self.chunking_model = ChatOpenAI(
            model="gpt-5",
            temperature=1,
            reasoning={"effort": "high"},
            api_key=openai_api_key,
        )
        
        self.chunking_prompt = self._create_chunking_prompt()
    
    def _create_chunking_prompt(self) -> str:
        """Create the prompt for intelligent chunking."""
        return """Você é um especialista em processamento de documentos para uma empresa de iluminação LED.
        
Sua tarefa é segmentar inteligentemente o documento em chunks semânticos que:
1. Preservem o contexto completo de cada informação
2. Identifiquem questões que cada chunk pode responder
3. Mantenham relacionamentos entre chunks relacionados
4. Sejam auto-contidos (compreensíveis isoladamente)

CONTEXTO DO NEGÓCIO:
- Empresa de iluminação LED para ambientes esportivos e industriais
- Clientes perguntam sobre produtos, preços, especificações, instalação
- Documento pode conter tabelas, listas, especificações técnicas

INSTRUÇÕES:
1. Divida o documento em chunks de 200-800 palavras (ideal: 400)
2. Cada chunk deve cobrir UM conceito completo ou produto
3. Preserve TODAS as informações técnicas (potência, lumens, IP, garantia)
4. Identifique 2-5 perguntas que cada chunk pode responder
5. Relacione chunks que se complementam

FORMATO DE SAÍDA (XML):
<chunks>
  <chunk id="chunk_001">
    <chunk_metadata>
      <about>Descrição breve do conteúdo</about>
      <category>product_specs|pricing|installation|warranty|technical|general</category>
      <keywords>palavras-chave, separadas, por, vírgula</keywords>
      <possible_questions>
        <question>Pergunta que este chunk responde?</question>
        <question>Outra pergunta relevante?</question>
      </possible_questions>
    </chunk_metadata>
    <chunk_content>
      Conteúdo real do chunk aqui...
    </chunk_content>
    <related_chunks>
      <related_chunk id="chunk_002">
        <relationship_reason>Por que está relacionado</relationship_reason>
      </related_chunk>
    </related_chunks>
  </chunk>
</chunks>

DOCUMENTO PARA PROCESSAR:
{document_content}

IMPORTANTE:
- Mantenha TODO o conteúdo em português (PT-BR)
- Tags XML podem ser em inglês
- Preserve números, preços, especificações EXATAMENTE
- Se houver tabelas, mantenha a estrutura clara
"""
    
    async def chunk_document(
        self,
        document_content: str,
        document_metadata: dict | None = None
    ) -> list[DocumentChunkData]:
        """Chunk a document using GPT-5 with high reasoning.
        
        Args:
            document_content: The document text to chunk
            document_metadata: Optional metadata about the document
            
        Returns:
            List of DocumentChunkData with semantic chunks
        """
        logger.info(f"Starting intelligent chunking for document ({len(document_content)} chars)")
        
        try:
            # Truncate if too long (GPT context limit)
            max_chars = 30000  # Conservative limit for GPT-4/5
            if len(document_content) > max_chars:
                logger.warning(f"Document truncated from {len(document_content)} to {max_chars} chars")
                document_content = document_content[:max_chars]
            
            # Call GPT-5 with high reasoning
            prompt = self.chunking_prompt.format(document_content=document_content)
            response = await self.chunking_model.ainvoke(prompt)
            
            # Handle GPT-5's different response format
            if isinstance(response.content, list):
                # GPT-5 returns list of dicts with 'text' field
                content_text = ""
                for item in response.content:
                    if isinstance(item, dict) and "text" in item:
                        content_text += item["text"]
                    else:
                        content_text += str(item)
            else:
                # GPT-4 returns plain string
                content_text = response.content
            
            # Parse XML response
            chunks = self._parse_xml_chunks(content_text)
            
            logger.info(f"Successfully created {len(chunks)} semantic chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Error in intelligent chunking: {e}")
            # Fallback to simple chunking
            return self._fallback_chunking(document_content)
    
    def _parse_xml_chunks(self, xml_content: str) -> list[DocumentChunkData]:
        """Parse XML response from GPT-5 into chunk objects.
        
        Args:
            xml_content: XML string from GPT-5
            
        Returns:
            List of parsed DocumentChunkData
        """
        chunks = []
        
        try:
            # First attempt: direct XML parsing
            xml_to_parse = xml_content.strip()
            
            # Handle common response formats from LLMs
            if not xml_to_parse.startswith("<"):
                # Extract XML from markdown code blocks more robustly
                # Look for ```xml or ``` blocks
                lines = xml_to_parse.split("\n")
                xml_lines = []
                in_code_block = False
                
                for line in lines:
                    if line.strip().startswith("```"):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block or line.strip().startswith("<"):
                        xml_lines.append(line)
                
                xml_to_parse = "\n".join(xml_lines).strip()
            
            # Validate we have something that looks like XML
            if not xml_to_parse.startswith("<chunks>"):
                # Try to find the chunks element anywhere in the content
                try:
                    # Use ET to parse partial document
                    for event, elem in ET.iterparse(io.StringIO(xml_content), events=["start", "end"]):
                        if elem.tag == "chunks" and event == "start":
                            # Found chunks element, reconstruct from here
                            xml_to_parse = ET.tostring(elem, encoding="unicode")
                            break
                except (OSError, ET.ParseError) as parse_error:
                    logger.debug(f"ET.iterparse failed: {parse_error}")
                    # Last resort: find chunks tags manually
                    start_idx = xml_to_parse.find("<chunks>")
                    end_idx = xml_to_parse.find("</chunks>")
                    if start_idx >= 0 and end_idx > start_idx:
                        xml_to_parse = xml_to_parse[start_idx:end_idx + len("</chunks>")]
                    else:
                        raise ValueError("No valid <chunks> element found in response")
            
            # Parse XML using ElementTree
            root = ET.fromstring(xml_to_parse)
            
            for chunk_elem in root.findall("chunk"):
                chunk_id = chunk_elem.get("id", f"chunk_{len(chunks):03d}")
                
                # Extract metadata
                metadata_elem = chunk_elem.find("chunk_metadata")
                metadata = ChunkMetadata(
                    about=self._get_text(metadata_elem, "about", "Chunk content"),
                    category=self._get_text(metadata_elem, "category", "general"),
                    keywords=self._get_text(metadata_elem, "keywords", ""),
                    possible_questions=self._get_questions(metadata_elem)
                )
                
                # Extract content
                content = self._get_text(chunk_elem, "chunk_content", "")
                
                # Extract relationships
                related_chunks = []
                related_elem = chunk_elem.find("related_chunks")
                if related_elem:
                    for rel in related_elem.findall("related_chunk"):
                        related_chunks.append({
                            "id": rel.get("id", ""),
                            "reason": self._get_text(rel, "relationship_reason", "")
                        })
                
                chunks.append(DocumentChunkData(
                    chunk_id=chunk_id,
                    content=content.strip(),
                    metadata=metadata,
                    related_chunks=related_chunks
                ))
            
        except ET.ParseError as e:
            logger.error(f"XML parsing error: {e}")
            # Return what we could parse or empty list
            if not chunks:
                raise ValueError(f"Invalid XML structure: {e}")
        except ValueError as e:
            logger.error(f"Value error parsing chunks: {e}")
            if not chunks:
                raise
        except Exception as e:
            logger.error(f"Unexpected error parsing XML chunks: {e}")
            # Return what we could parse or empty list
            if not chunks:
                raise ValueError(f"Failed to parse chunks from XML: {e}")
        
        return chunks
    
    def _get_text(self, parent: ET.Element | None, tag: str, default: str = "") -> str:
        """Safely extract text from XML element."""
        if parent is None:
            return default
        elem = parent.find(tag)
        return elem.text.strip() if elem is not None and elem.text else default
    
    def _get_questions(self, metadata_elem: ET.Element | None) -> list[str]:
        """Extract possible questions from metadata element."""
        questions = []
        if metadata_elem is None:
            return questions
        
        questions_elem = metadata_elem.find("possible_questions")
        if questions_elem:
            for q in questions_elem.findall("question"):
                if q.text:
                    questions.append(q.text.strip())
        
        return questions if questions else ["Informação geral sobre o conteúdo"]
    
    def _fallback_chunking(self, content: str, chunk_size: int = 500) -> list[DocumentChunkData]:
        """Simple fallback chunking by size.
        
        Args:
            content: Document content
            chunk_size: Target words per chunk
            
        Returns:
            List of simple chunks
        """
        logger.warning("Using fallback chunking strategy")
        
        words = content.split()
        chunks = []
        
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            
            chunks.append(DocumentChunkData(
                chunk_id=f"chunk_{len(chunks):03d}",
                content=chunk_text,
                metadata=ChunkMetadata(
                    about=f"Seção {len(chunks) + 1} do documento",
                    category="general",
                    keywords="",
                    possible_questions=["Informação geral sobre o conteúdo"]
                ),
                related_chunks=[]
            ))
        
        return chunks
    
    def optimize_chunks(self, chunks: list[DocumentChunkData]) -> list[DocumentChunkData]:
        """Post-process chunks to optimize for retrieval.
        
        Args:
            chunks: Initial chunks from GPT-5
            
        Returns:
            Optimized chunks
        """
        # Ensure minimum chunk size
        min_words = 50
        optimized = []
        buffer = None
        
        for chunk in chunks:
            word_count = len(chunk.content.split())
            
            if word_count < min_words:
                # Merge small chunks
                if buffer:
                    buffer.content += f"\n\n{chunk.content}"
                    buffer.metadata.possible_questions.extend(chunk.metadata.possible_questions)
                    buffer.related_chunks.extend(chunk.related_chunks)
                else:
                    buffer = chunk
            else:
                if buffer:
                    optimized.append(buffer)
                    buffer = None
                optimized.append(chunk)
        
        if buffer:
            optimized.append(buffer)
        
        # Re-index chunks
        for i, chunk in enumerate(optimized):
            chunk.chunk_id = f"chunk_{i:03d}"
        
        return optimized
