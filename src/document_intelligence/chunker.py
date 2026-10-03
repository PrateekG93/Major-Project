"""
Structure-Aware Text Chunker
=============================
Module 1 - Document Intelligence (Part 2)

Splits parsed documents into semantically meaningful chunks based on:
- Heading boundaries (Markdown-style # headers)
- Slide boundaries (for PPTX)
- Configurable chunk size with overlap
- Metadata enrichment (source file, section, page, doc_type)
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from src.document_intelligence.parser import DocumentContent
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default chunking parameters
DEFAULT_CHUNK_SIZE = 512  # target words per chunk
DEFAULT_OVERLAP = 64  # overlap words between consecutive chunks


@dataclass
class TextChunk:
    """A single text chunk with full metadata for retrieval."""

    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """
    Split text by Markdown-style headings.

    Returns:
        List of (heading, section_text) tuples.
    """
    # Match lines starting with 1-6 # characters
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(text))

    if not matches:
        return [("", text)]

    sections = []
    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        if section_text:
            sections.append((heading, section_text))

    # Include any text before the first heading
    pre_heading_text = text[: matches[0].start()].strip()
    if pre_heading_text:
        sections.insert(0, ("Introduction", pre_heading_text))

    return sections


def _split_by_size(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """
    Split text into word-count-based chunks with overlap.

    Args:
        text: Input text to split.
        chunk_size: Target number of words per chunk.
        overlap: Number of overlapping words between consecutive chunks.

    Returns:
        List of text chunk strings.
    """
    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_text = " ".join(words[start:end])
        chunks.append(chunk_text)

        # Move forward by (chunk_size - overlap) words
        start += chunk_size - overlap
        if start >= len(words):
            break

    return chunks


def chunk_document(
    document: DocumentContent,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    doc_type: Optional[str] = None,
) -> list[TextChunk]:
    """
    Split a parsed document into metadata-enriched text chunks.

    Strategy:
    1. For PPTX: Each slide becomes one chunk (or is split if too large).
    2. For other formats: Split by headings first, then by size.
    3. Each chunk is tagged with source filename, section, page, and doc_type.

    Args:
        document: Parsed DocumentContent from the parser module.
        chunk_size: Target words per chunk.
        overlap: Overlap words between consecutive chunks.
        doc_type: Override document type tag.

    Returns:
        List of TextChunk objects ready for embedding and indexing.
    """
    effective_doc_type = doc_type or document.doc_type
    chunks: list[TextChunk] = []

    if document.file_format == "pptx":
        # PPTX: One chunk per slide, split large slides
        for page in document.pages:
            if not page.text.strip():
                continue

            slide_chunks = _split_by_size(page.text, chunk_size, overlap)
            for i, chunk_text in enumerate(slide_chunks):
                chunks.append(
                    TextChunk(
                        chunk_id=str(uuid.uuid4()),
                        text=chunk_text,
                        metadata={
                            "source_file": document.filename,
                            "doc_type": effective_doc_type,
                            "slide": page.page_number,
                            "chunk_index": i,
                            "section": f"Slide {page.page_number}",
                        },
                    )
                )
    else:
        # PDF / DOCX / TXT: Combine all pages, split by headings, then by size
        full_text = document.full_text

        if not full_text.strip():
            logger.warning(f"Empty document: {document.filename}")
            return []

        sections = _split_by_headings(full_text)

        for heading, section_text in sections:
            section_chunks = _split_by_size(section_text, chunk_size, overlap)

            for i, chunk_text in enumerate(section_chunks):
                # Try to determine the page number from the original document
                page_num = _estimate_page(document, chunk_text)

                chunks.append(
                    TextChunk(
                        chunk_id=str(uuid.uuid4()),
                        text=chunk_text,
                        metadata={
                            "source_file": document.filename,
                            "doc_type": effective_doc_type,
                            "section": heading or "General",
                            "page": page_num,
                            "chunk_index": i,
                        },
                    )
                )

    logger.info(
        f"Chunked '{document.filename}': {len(chunks)} chunks "
        f"(chunk_size={chunk_size}, overlap={overlap})"
    )
    return chunks


def _estimate_page(document: DocumentContent, chunk_text: str) -> int:
    """
    Estimate which page a chunk came from by checking text overlap.

    Args:
        document: The source document.
        chunk_text: The chunk text to locate.

    Returns:
        Best-guess page number (1-indexed), or 1 if undetermined.
    """
    # Use first 50 characters of the chunk to match against pages
    snippet = chunk_text[:50].strip()
    if not snippet:
        return 1

    for page in document.pages:
        if snippet in page.text:
            return page.page_number

    return 1
