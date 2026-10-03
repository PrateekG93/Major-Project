"""
Multi-Format Document Parser
=============================
Module 1 - Document Intelligence (Part 1)

Extracts text content from heterogeneous academic documents:
- PDF (.pdf) via PyPDF2
- Word (.docx) via python-docx
- PowerPoint (.pptx) via python-pptx
- Plain text (.txt, .md) via native file read
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PageContent:
    """Represents content from a single page/slide of a document."""

    page_number: int
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class DocumentContent:
    """Complete parsed content of a document with metadata."""

    filename: str
    file_format: str
    total_pages: int
    pages: list[PageContent]
    doc_type: str = "notes"  # syllabus | notes | resume | exam
    raw_text: str = ""

    @property
    def full_text(self) -> str:
        """Concatenate all pages into a single text blob."""
        if self.raw_text:
            return self.raw_text
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


def parse_pdf(file_path: str) -> DocumentContent:
    """
    Extract text from a PDF file using PyPDF2.

    Args:
        file_path: Absolute or relative path to the PDF file.

    Returns:
        DocumentContent with per-page text extraction.
    """
    from PyPDF2 import PdfReader

    logger.info(f"Parsing PDF: {file_path}")
    reader = PdfReader(file_path)
    pages = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(
            PageContent(
                page_number=i + 1,
                text=text.strip(),
                metadata={"source": os.path.basename(file_path), "page": i + 1},
            )
        )

    logger.info(f"PDF parsed: {len(pages)} pages extracted from {file_path}")
    return DocumentContent(
        filename=os.path.basename(file_path),
        file_format="pdf",
        total_pages=len(pages),
        pages=pages,
    )


def parse_docx(file_path: str) -> DocumentContent:
    """
    Extract text from a Word (.docx) file.

    Args:
        file_path: Path to the .docx file.

    Returns:
        DocumentContent with paragraph-based content.
    """
    from docx import Document

    logger.info(f"Parsing DOCX: {file_path}")
    doc = Document(file_path)

    # Group paragraphs into logical sections
    full_text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())

    pages = [
        PageContent(
            page_number=1,
            text=full_text,
            metadata={"source": os.path.basename(file_path)},
        )
    ]

    logger.info(f"DOCX parsed: {len(doc.paragraphs)} paragraphs from {file_path}")
    return DocumentContent(
        filename=os.path.basename(file_path),
        file_format="docx",
        total_pages=1,
        pages=pages,
    )


def parse_pptx(file_path: str) -> DocumentContent:
    """
    Extract text from a PowerPoint (.pptx) file, one slide per page.

    Args:
        file_path: Path to the .pptx file.

    Returns:
        DocumentContent with one PageContent per slide.
    """
    from pptx import Presentation

    logger.info(f"Parsing PPTX: {file_path}")
    prs = Presentation(file_path)
    pages = []

    for i, slide in enumerate(prs.slides):
        slide_texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    text = paragraph.text.strip()
                    if text:
                        slide_texts.append(text)

        pages.append(
            PageContent(
                page_number=i + 1,
                text="\n".join(slide_texts),
                metadata={
                    "source": os.path.basename(file_path),
                    "slide": i + 1,
                },
            )
        )

    logger.info(f"PPTX parsed: {len(pages)} slides from {file_path}")
    return DocumentContent(
        filename=os.path.basename(file_path),
        file_format="pptx",
        total_pages=len(pages),
        pages=pages,
    )


def parse_text(file_path: str) -> DocumentContent:
    """
    Read a plain text or markdown file.

    Args:
        file_path: Path to .txt or .md file.

    Returns:
        DocumentContent with full file content as a single page.
    """
    logger.info(f"Parsing text file: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    ext = Path(file_path).suffix.lstrip(".")
    pages = [
        PageContent(
            page_number=1,
            text=content.strip(),
            metadata={"source": os.path.basename(file_path)},
        )
    ]

    return DocumentContent(
        filename=os.path.basename(file_path),
        file_format=ext,
        total_pages=1,
        pages=pages,
        raw_text=content.strip(),
    )


# ---------------------------------------------------------------------------
# Dispatcher: route file to the correct parser based on extension
# ---------------------------------------------------------------------------

SUPPORTED_FORMATS = {".pdf", ".docx", ".pptx", ".txt", ".md"}

_PARSER_MAP = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".pptx": parse_pptx,
    ".txt": parse_text,
    ".md": parse_text,
}


def parse_document(
    file_path: str, doc_type: Optional[str] = None
) -> DocumentContent:
    """
    Parse any supported document format.

    Args:
        file_path: Path to the document file.
        doc_type: Optional category tag — one of 'syllabus', 'notes', 'resume', 'exam'.

    Returns:
        Parsed DocumentContent with text, pages, and metadata.

    Raises:
        ValueError: If the file format is not supported.
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Document not found: {file_path}")

    ext = Path(file_path).suffix.lower()
    if ext not in _PARSER_MAP:
        raise ValueError(
            f"Unsupported format '{ext}'. Supported: {SUPPORTED_FORMATS}"
        )

    parser_fn = _PARSER_MAP[ext]

    try:
        doc = parser_fn(file_path)
        if doc_type:
            doc.doc_type = doc_type
        return doc
    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}")
        # Graceful degradation: return empty document rather than crashing
        logger.warning(f"Returning empty document for {file_path} due to parse error")
        return DocumentContent(
            filename=os.path.basename(file_path),
            file_format=ext.lstrip("."),
            total_pages=0,
            pages=[],
            doc_type=doc_type or "notes",
        )
