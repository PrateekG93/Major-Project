"""
Tests for Document Intelligence Module
========================================
Tests document parsing across PDF, DOCX, PPTX, and TXT formats,
and text chunking with metadata enrichment.
"""

import os
import tempfile

import pytest

from src.document_intelligence.parser import (
    parse_document,
    parse_text,
    DocumentContent,
    SUPPORTED_FORMATS,
)
from src.document_intelligence.chunker import (
    chunk_document,
    TextChunk,
    _split_by_headings,
    _split_by_size,
)


class TestParser:
    """Tests for the document parser."""

    def test_parse_text_file(self, tmp_path):
        """Test parsing a plain text file."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello world.\nThis is a test document.\nWith multiple lines.")

        doc = parse_document(str(txt_file), doc_type="notes")

        assert isinstance(doc, DocumentContent)
        assert doc.filename == "test.txt"
        assert doc.file_format == "txt"
        assert doc.doc_type == "notes"
        assert doc.total_pages == 1
        assert "Hello world" in doc.full_text

    def test_parse_markdown_file(self, tmp_path):
        """Test parsing a markdown file."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Heading\n\nSome content here.\n\n## Subheading\n\nMore content.")

        doc = parse_document(str(md_file), doc_type="syllabus")

        assert doc.file_format == "md"
        assert doc.doc_type == "syllabus"
        assert "Heading" in doc.full_text

    def test_unsupported_format_raises(self, tmp_path):
        """Test that unsupported formats raise ValueError."""
        bad_file = tmp_path / "test.xyz"
        bad_file.write_text("content")

        with pytest.raises(ValueError, match="Unsupported format"):
            parse_document(str(bad_file))

    def test_file_not_found_raises(self):
        """Test that missing files raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_document("/nonexistent/path/file.pdf")

    def test_supported_formats_constant(self):
        """Test that supported formats are correctly defined."""
        assert ".pdf" in SUPPORTED_FORMATS
        assert ".docx" in SUPPORTED_FORMATS
        assert ".pptx" in SUPPORTED_FORMATS
        assert ".txt" in SUPPORTED_FORMATS
        assert ".md" in SUPPORTED_FORMATS

    def test_doc_type_assignment(self, tmp_path):
        """Test that doc_type is correctly assigned."""
        txt_file = tmp_path / "resume.txt"
        txt_file.write_text("Skills: Python, ML, SQL")

        doc = parse_document(str(txt_file), doc_type="resume")
        assert doc.doc_type == "resume"


class TestChunker:
    """Tests for the text chunker."""

    def test_split_by_headings(self):
        """Test heading-based text splitting."""
        text = "# Introduction\nHello world.\n# Methods\nSome methods here.\n# Results\nResults text."
        sections = _split_by_headings(text)

        assert len(sections) >= 3
        assert any("Introduction" in s[0] for s in sections)
        assert any("Methods" in s[0] for s in sections)

    def test_split_by_size(self):
        """Test size-based text splitting."""
        # Create text longer than chunk_size
        text = " ".join(["word"] * 100)
        chunks = _split_by_size(text, chunk_size=30, overlap=5)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.split()) <= 35  # chunk_size + some tolerance

    def test_split_by_size_short_text(self):
        """Test that short text returns a single chunk."""
        text = "This is a short text."
        chunks = _split_by_size(text, chunk_size=100)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_document(self, tmp_path):
        """Test full document chunking pipeline."""
        txt_file = tmp_path / "course.txt"
        txt_file.write_text(
            "# Unit 1: Introduction\n"
            "This is the introduction to the course. " * 50 + "\n"
            "# Unit 2: Advanced Topics\n"
            "Advanced content goes here. " * 50
        )

        doc = parse_document(str(txt_file), doc_type="syllabus")
        chunks = chunk_document(doc, chunk_size=50, overlap=10)

        assert len(chunks) > 0
        assert all(isinstance(c, TextChunk) for c in chunks)

        # Check metadata
        for chunk in chunks:
            assert "source_file" in chunk.metadata
            assert "doc_type" in chunk.metadata
            assert chunk.metadata["doc_type"] == "syllabus"

    def test_chunk_has_unique_ids(self, tmp_path):
        """Test that each chunk gets a unique ID."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Content " * 200)

        doc = parse_document(str(txt_file))
        chunks = chunk_document(doc, chunk_size=30)

        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))  # All unique

    def test_empty_document_returns_no_chunks(self, tmp_path):
        """Test that empty documents produce no chunks."""
        txt_file = tmp_path / "empty.txt"
        txt_file.write_text("")

        doc = parse_document(str(txt_file))
        chunks = chunk_document(doc)

        assert len(chunks) == 0
