"""
Tests for RAG Assistant Module
================================
Tests the hybrid retriever (BM25 + vector fusion) and embedding pipeline.
"""

import pytest
import numpy as np

from src.document_intelligence.chunker import TextChunk


class TestEmbeddings:
    """Tests for the embedding engine."""

    def test_embed_query_returns_array(self):
        """Test that embed_query returns a numpy array."""
        from src.rag_assistant.embeddings import embed_query
        result = embed_query("What is machine learning?")
        assert isinstance(result, np.ndarray)
        assert len(result.shape) == 1
        assert result.shape[0] > 0

    def test_embed_texts_batch(self):
        """Test batch embedding of multiple texts."""
        from src.rag_assistant.embeddings import embed_texts
        texts = ["Hello world", "Machine learning is great", "Python programming"]
        result = embed_texts(texts)
        assert isinstance(result, np.ndarray)
        assert result.shape[0] == 3

    def test_cosine_similarity_identical(self):
        """Test cosine similarity of identical vectors."""
        from src.rag_assistant.embeddings import embed_query, cosine_similarity
        emb = embed_query("test query")
        sim = cosine_similarity(emb, emb)
        assert abs(sim - 1.0) < 0.01  # Should be ~1.0

    def test_similar_texts_higher_similarity(self):
        """Test that semantically similar texts have higher similarity."""
        from src.rag_assistant.embeddings import embed_query, cosine_similarity

        emb1 = embed_query("machine learning algorithms")
        emb2 = embed_query("ML and AI methods")
        emb3 = embed_query("cooking recipes for dinner")

        sim_related = cosine_similarity(emb1, emb2)
        sim_unrelated = cosine_similarity(emb1, emb3)

        assert sim_related > sim_unrelated


class TestHybridRetriever:
    """Tests for the hybrid retriever."""

    @pytest.fixture
    def sample_chunks(self):
        """Create sample chunks for testing."""
        return [
            TextChunk(
                chunk_id="chunk_001",
                text="Principal Component Analysis (PCA) is a dimensionality reduction technique that transforms data into orthogonal components.",
                metadata={"source_file": "ml_notes.pdf", "doc_type": "notes", "section": "PCA"},
            ),
            TextChunk(
                chunk_id="chunk_002",
                text="Random Forest is an ensemble learning method that builds multiple decision trees and merges their predictions.",
                metadata={"source_file": "ml_notes.pdf", "doc_type": "notes", "section": "Ensemble Methods"},
            ),
            TextChunk(
                chunk_id="chunk_003",
                text="SQL JOIN operations combine rows from two or more tables based on a related column. INNER JOIN returns matching rows.",
                metadata={"source_file": "dbms_notes.pdf", "doc_type": "notes", "section": "SQL Joins"},
            ),
        ]

    def test_add_and_search(self, sample_chunks):
        """Test adding documents and searching."""
        from src.rag_assistant.hybrid_retriever import HybridRetriever

        retriever = HybridRetriever(collection_name="test_collection")
        try:
            num = retriever.add_documents(sample_chunks)
            assert num == 3

            results = retriever.search("What is PCA?", top_k=2)
            assert len(results) > 0
            assert results[0]["text"]  # Should have text content

        finally:
            retriever.delete_collection()

    def test_empty_collection_search(self):
        """Test searching an empty collection returns empty results."""
        from src.rag_assistant.hybrid_retriever import HybridRetriever

        retriever = HybridRetriever(collection_name="empty_test")
        try:
            results = retriever.search("anything")
            assert len(results) == 0
        finally:
            retriever.delete_collection()

    def test_document_count(self, sample_chunks):
        """Test document count tracking."""
        from src.rag_assistant.hybrid_retriever import HybridRetriever

        retriever = HybridRetriever(collection_name="count_test")
        try:
            assert retriever.get_document_count() == 0
            retriever.add_documents(sample_chunks)
            assert retriever.get_document_count() == 3
        finally:
            retriever.delete_collection()
