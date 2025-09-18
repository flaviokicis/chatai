"""Document parsing service for various file formats.

This service handles parsing of different document types (PDF, Markdown, Text)
and prepares them for intelligent chunking.
"""

import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Optional
from markitdown import MarkItDown
import re

logger = logging.getLogger(__name__)


class DocumentType(str, Enum):
    """Supported document types."""
    PDF = "pdf"
    MARKDOWN = "md"
    TEXT = "txt"
    XML = "xml"
    HTML = "html"
    JSON = "json"
    UNKNOWN = "unknown"


class ParsedDocument:
    """Represents a parsed document with metadata."""
    
    def __init__(
        self,
        content: str,
        file_name: str,
        file_type: DocumentType,
        metadata: Optional[Dict] = None
    ):
        self.content = content
        self.file_name = file_name
        self.file_type = file_type
        self.metadata = metadata or {}
        self.char_count = len(content)
        self.word_count = len(content.split())
        self.line_count = len(content.splitlines())


class DocumentParserService:
    """Service for parsing various document formats.
    
    This service uses Microsoft's MarkItDown for robust document parsing,
    especially for messy PDFs and complex formats.
    """
    
    def __init__(self):
        """Initialize the document parser service."""
        self.markitdown = MarkItDown()
        self._encoding_fixes = {
            "(cid:127)": "•",  # Bullet point
            "(cid:128)": "€",  # Euro symbol
            "(cid:129)": "",   # Control character
        }
    
    def parse_document(self, file_path: str) -> ParsedDocument:
        """Parse a document from file path.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            ParsedDocument with extracted content and metadata
            
        Raises:
            ValueError: If file type is not supported
            FileNotFoundError: If file doesn't exist
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        file_type = self._detect_file_type(path)
        logger.info(f"Parsing {file_type.value} document: {path.name}")
        
        try:
            # Use MarkItDown for all document types
            result = self.markitdown.convert(str(path))
            content = result.text_content
            
            # Clean up encoding artifacts
            content = self._clean_content(content)
            
            # Extract basic metadata
            metadata = {
                "file_size": path.stat().st_size,
                "file_path": str(path),
                "title": result.title if hasattr(result, 'title') else path.stem,
            }
            
            return ParsedDocument(
                content=content,
                file_name=path.name,
                file_type=file_type,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Error parsing document {path.name}: {e}")
            # Fallback to basic text reading for simple formats
            if file_type in [DocumentType.TEXT, DocumentType.MARKDOWN]:
                content = path.read_text(encoding='utf-8')
                return ParsedDocument(
                    content=content,
                    file_name=path.name,
                    file_type=file_type,
                    metadata={"file_size": path.stat().st_size}
                )
            raise
    
    def parse_text(self, text: str, file_name: str = "inline_text") -> ParsedDocument:
        """Parse text content directly.
        
        Args:
            text: Text content to parse
            file_name: Optional file name for identification
            
        Returns:
            ParsedDocument with the text content
        """
        content = self._clean_content(text)
        return ParsedDocument(
            content=content,
            file_name=file_name,
            file_type=DocumentType.TEXT,
            metadata={"source": "direct_text"}
        )
    
    def _detect_file_type(self, path: Path) -> DocumentType:
        """Detect document type from file extension.
        
        Args:
            path: Path to the file
            
        Returns:
            Detected DocumentType
        """
        suffix = path.suffix.lower()
        type_mapping = {
            '.pdf': DocumentType.PDF,
            '.md': DocumentType.MARKDOWN,
            '.txt': DocumentType.TEXT,
            '.xml': DocumentType.XML,
            '.html': DocumentType.HTML,
            '.htm': DocumentType.HTML,
            '.json': DocumentType.JSON,
        }
        return type_mapping.get(suffix, DocumentType.UNKNOWN)
    
    def _clean_content(self, content: str) -> str:
        """Clean content from encoding artifacts and normalize.
        
        Args:
            content: Raw content
            
        Returns:
            Cleaned content
        """
        # Fix known encoding issues
        for artifact, replacement in self._encoding_fixes.items():
            content = content.replace(artifact, replacement)
        
        # Normalize whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)  # Max 2 newlines
        content = re.sub(r' {2,}', ' ', content)  # Single spaces
        content = content.strip()
        
        return content
    
    def extract_structured_data(self, document: ParsedDocument) -> Dict:
        """Extract structured data from document if possible.
        
        Args:
            document: Parsed document
            
        Returns:
            Dictionary with extracted structured data
        """
        structured_data = {
            "tables": [],
            "lists": [],
            "headers": [],
            "links": [],
        }
        
        lines = document.content.splitlines()
        
        # Extract headers (lines that look like headers)
        header_patterns = [
            r'^#{1,6}\s+(.+)$',  # Markdown headers
            r'^([A-Z][A-Z\s]+):?\s*$',  # ALL CAPS headers
            r'^(\d+\.?\s+[A-Z].+)$',  # Numbered headers
        ]
        
        for line in lines:
            for pattern in header_patterns:
                match = re.match(pattern, line)
                if match:
                    structured_data["headers"].append(match.group(1).strip())
                    break
        
        # Extract lists (basic detection)
        list_patterns = [
            r'^\s*[-*•]\s+(.+)$',  # Bullet points
            r'^\s*\d+\.\s+(.+)$',  # Numbered lists
        ]
        
        for line in lines:
            for pattern in list_patterns:
                match = re.match(pattern, line)
                if match:
                    structured_data["lists"].append(match.group(1).strip())
                    break
        
        # Extract URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, document.content)
        structured_data["links"] = list(set(urls))
        
        return structured_data
