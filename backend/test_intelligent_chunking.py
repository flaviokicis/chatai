#!/usr/bin/env python3
"""
Intelligent document chunking using MarkItDown and GPT-5 reasoning.
Simulates real-world RAG preprocessing with smart chunk creation.
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from markitdown import MarkItDown

# Load environment variables
load_dotenv()


def parse_pdf_with_markitdown(pdf_path: Path) -> str:
    """Parse PDF using Microsoft's MarkItDown."""
    md = MarkItDown()
    result = md.convert(str(pdf_path))
    return result.text_content


def create_chunking_prompt(document_content: str, doc_name: str) -> str:
    """Create a sophisticated prompt for GPT-5 to intelligently chunk documents."""

    prompt = f"""You are an expert document analyst preparing content for a RAG (Retrieval-Augmented Generation) system for an LED lighting company. 
    
Your task is to intelligently chunk the following document into semantic units that will be useful for answering customer questions about LED products, installation, pricing, and technical specifications.

DOCUMENT NAME: {doc_name}
DOCUMENT CONTENT:
{document_content}

CHUNKING REQUIREMENTS:
1. Each chunk should be a self-contained unit of information
2. Preserve important context and relationships
3. Include metadata about what each chunk contains
4. Identify potential customer questions that each chunk could answer
5. Link related chunks that should be retrieved together
6. Chunks should be 100-500 words typically, but can be longer for complete tables or specifications

OUTPUT FORMAT:
Generate XML with the following structure for EACH chunk. Create as many chunks as needed to properly segment the document:

<chunks>
<chunk id="chunk_001">
  <chunk_metadata>
    <about>Brief description of what this chunk contains</about>
    <category>One of: product_specs, pricing, installation, technical, warranty, comparison, general_info</category>
    <keywords>comma, separated, relevant, keywords</keywords>
    <possible_questions>
      <question id="q1">Example question this chunk answers</question>
      <question id="q2">Another relevant question</question>
    </possible_questions>
  </chunk_metadata>
  <chunk_content>
    The actual content from the document goes here. Preserve important details, numbers, specifications.
  </chunk_content>
  <related_chunks>
    <related_chunk id="chunk_002">
      <relationship_reason>Why this chunk is related and when it should be fetched together</relationship_reason>
    </related_chunk>
  </related_chunks>
</chunk>
<!-- Continue with more chunks... -->
</chunks>

IMPORTANT GUIDELINES:
- For product specifications, keep model numbers, wattage, lumens together
- For pricing information, include payment terms and conditions in the same or linked chunks  
- For installation guides, maintain step sequences but can split into logical sections
- For comparisons or tables, try to keep complete tables in single chunks
- Identify cross-references between chunks (e.g., a product mentioned in catalog linking to its installation guide)
- Consider the sales flow from the fluxo_luminarias.json - chunks should help answer questions at each decision point

Be thorough and create as many chunks as needed to properly organize the information."""

    return prompt


async def chunk_document_with_gpt5(document_content: str, doc_name: str) -> str:
    """Use GPT-5 with high reasoning to intelligently chunk the document."""

    model = ChatOpenAI(
        model="gpt-5",
        model_kwargs={"reasoning": {"effort": "high"}},  # High reasoning for complex analysis
        temperature=0,
        max_tokens=8000,  # Allow for extensive output
    )

    prompt = create_chunking_prompt(document_content, doc_name)

    print(f"🤔 GPT-5 is analyzing and chunking {doc_name} with high reasoning effort...")
    print("This may take 30-60 seconds due to high reasoning mode...")

    response = await model.ainvoke(prompt)

    # Extract content
    if isinstance(response.content, list) and len(response.content) > 0:
        if isinstance(response.content[0], dict) and "text" in response.content[0]:
            return response.content[0]["text"]
    return str(response.content)


def extract_chunks_from_xml(xml_content: str) -> list[dict[str, Any]]:
    """Parse the XML output to extract chunks as structured data."""
    chunks = []

    # Simple regex-based extraction (in production, use proper XML parser)
    chunk_pattern = r'<chunk id="([^"]+)">(.*?)</chunk>'
    matches = re.findall(chunk_pattern, xml_content, re.DOTALL)

    for chunk_id, chunk_content in matches:
        # Extract metadata
        about_match = re.search(r"<about>(.*?)</about>", chunk_content, re.DOTALL)
        category_match = re.search(r"<category>(.*?)</category>", chunk_content)
        content_match = re.search(r"<chunk_content>(.*?)</chunk_content>", chunk_content, re.DOTALL)

        chunk_data = {
            "id": chunk_id,
            "about": about_match.group(1).strip() if about_match else "",
            "category": category_match.group(1).strip() if category_match else "",
            "content": content_match.group(1).strip() if content_match else "",
            "content_length": len(content_match.group(1).strip()) if content_match else 0,
        }

        # Extract questions
        questions = re.findall(r"<question[^>]*>(.*?)</question>", chunk_content)
        chunk_data["possible_questions"] = questions

        # Extract related chunks
        related = re.findall(
            r'<related_chunk id="([^"]+)">\s*<relationship_reason>(.*?)</relationship_reason>',
            chunk_content,
            re.DOTALL,
        )
        chunk_data["related_chunks"] = [{"id": r[0], "reason": r[1].strip()} for r in related]

        chunks.append(chunk_data)

    return chunks


async def process_single_document(pdf_path: Path) -> dict[str, Any]:
    """Process a single PDF document through the entire pipeline."""

    print(f"\n{'=' * 70}")
    print(f"📄 Processing: {pdf_path.name}")
    print(f"{'=' * 70}")

    # Step 1: Parse PDF with MarkItDown
    print("1️⃣ Parsing PDF with MarkItDown...")
    try:
        content = parse_pdf_with_markitdown(pdf_path)
        print(f"   ✅ Extracted {len(content)} characters")
    except Exception as e:
        print(f"   ❌ Error parsing PDF: {e}")
        return {"error": str(e)}

    # Show preview of extracted content
    print("\n   📝 Content preview (first 500 chars):")
    print(f"   {'-' * 60}")
    preview = content[:500].replace("\n", "\n   ")
    print(f"   {preview}...")
    print(f"   {'-' * 60}")

    # Step 2: Chunk with GPT-5
    print("\n2️⃣ Intelligent chunking with GPT-5 (high reasoning)...")
    try:
        xml_output = await chunk_document_with_gpt5(content, pdf_path.name)
        print(f"   ✅ Generated XML output ({len(xml_output)} characters)")
    except Exception as e:
        print(f"   ❌ Error chunking with GPT-5: {e}")
        return {"error": str(e)}

    # Step 3: Parse chunks
    print("\n3️⃣ Parsing chunk structure...")
    chunks = extract_chunks_from_xml(xml_output)
    print(f"   ✅ Extracted {len(chunks)} chunks")

    # Display chunk analysis
    if chunks:
        print("\n📊 Chunk Analysis:")
        print(f"   {'-' * 60}")

        categories = {}
        total_questions = 0
        total_relations = 0

        for i, chunk in enumerate(chunks[:5], 1):  # Show first 5 chunks
            print(f"\n   Chunk #{i} (ID: {chunk['id']})")
            print(f"   About: {chunk['about'][:100]}...")
            print(f"   Category: {chunk['category']}")
            print(f"   Content length: {chunk['content_length']} chars")
            print(f"   Questions it answers: {len(chunk.get('possible_questions', []))}")
            if chunk.get("possible_questions"):
                for q in chunk["possible_questions"][:2]:
                    print(f"      - {q[:80]}...")
            print(f"   Related chunks: {len(chunk.get('related_chunks', []))}")

            # Collect stats
            cat = chunk.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
            total_questions += len(chunk.get("possible_questions", []))
            total_relations += len(chunk.get("related_chunks", []))

        if len(chunks) > 5:
            print(f"\n   ... and {len(chunks) - 5} more chunks")

        print("\n   📈 Summary Statistics:")
        print(f"   Total chunks: {len(chunks)}")
        print(f"   Categories: {dict(categories)}")
        print(f"   Total questions identified: {total_questions}")
        print(f"   Total chunk relationships: {total_relations}")
        print(
            f"   Avg chunk size: {sum(c['content_length'] for c in chunks) / len(chunks):.0f} chars"
        )

    return {
        "document": pdf_path.name,
        "original_length": len(content),
        "chunks": chunks,
        "xml_output": xml_output,
    }


async def main():
    """Process all PDF documents and analyze chunking quality."""

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        return

    # Find PDFs
    pdf_dir = Path("/Users/jessica/me/chatai/backend/playground/documents/pdfs")
    pdf_files = list(pdf_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"❌ No PDF files found in {pdf_dir}")
        return

    print("🚀 Intelligent Document Chunking Pipeline")
    print(f"Found {len(pdf_files)} PDF documents to process")

    # Process documents (one at a time due to high reasoning computational cost)
    # In production, you might want to batch or parallelize with limits

    # Let's process the most complex/interesting documents
    priority_docs = [
        "catalogo_luminarias_desordenado.pdf",  # Messy catalog
        "manual_instalacao_confuso.pdf",  # Technical manual
        "orcamento_ginasio.pdf",  # Structured quote
    ]

    results = []
    for doc_name in priority_docs:
        pdf_path = pdf_dir / doc_name
        if pdf_path.exists():
            result = await process_single_document(pdf_path)
            results.append(result)

            # Save the XML output for inspection
            if "xml_output" in result:
                output_path = pdf_dir / f"{pdf_path.stem}_chunks.xml"
                output_path.write_text(result["xml_output"])
                print(f"\n💾 Saved chunk XML to: {output_path}")

    # Final summary
    print(f"\n{'=' * 70}")
    print("🎯 CHUNKING PIPELINE COMPLETE")
    print(f"{'=' * 70}")
    print(f"Processed {len(results)} documents")
    print(f"Total chunks created: {sum(len(r.get('chunks', [])) for r in results)}")
    print("\n✅ Ready for vector embedding and RAG implementation!")


if __name__ == "__main__":
    asyncio.run(main())




