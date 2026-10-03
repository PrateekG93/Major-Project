"""
Hybrid Retriever
================
Module 2 - RAG Assistant (Part 2)

Combines two retrieval strategies with Reciprocal Rank Fusion (RRF):
1. BM25 (sparse lexical matching) — catches exact keywords, acronyms, algorithm names
2. ChromaDB (dense vector similarity) — captures semantic meaning

The fused results maximize both precision and recall before being sent to the LLM.
"""

import os
from typing import Optional

import chromadb
import numpy as np
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

from src.document_intelligence.chunker import TextChunk
from src.rag_assistant.embeddings import embed_query, embed_texts
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/vector_store/chroma")


class HybridRetriever:
    """
    Hybrid BM25 + Dense Vector retriever with Reciprocal Rank Fusion.

    Usage:
        retriever = HybridRetriever(collection_name="user_docs")
        retriever.add_documents(chunks)
        results = retriever.search("What is PCA?", top_k=5)
    """

    def __init__(self, collection_name: str = "default"):
        """
        Initialize the hybrid retriever.

        Args:
            collection_name: ChromaDB collection name for this document set.
        """
        self.collection_name = collection_name

        # Initialize ChromaDB persistent client
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        self._chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        self._collection = self._chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # BM25 index (in-memory, rebuilt from stored documents)
        self._bm25_corpus: list[list[str]] = []  # tokenized docs
        self._bm25_index: Optional[BM25Okapi] = None
        self._chunk_map: dict[str, TextChunk] = {}  # chunk_id -> TextChunk

        # Rebuild BM25 from existing ChromaDB data
        self._rebuild_bm25_from_chroma()

        logger.info(
            f"HybridRetriever initialized: collection='{collection_name}', "
            f"docs={self._collection.count()}"
        )

    def _rebuild_bm25_from_chroma(self) -> None:
        """Rebuild the BM25 index from documents already stored in ChromaDB."""
        count = self._collection.count()
        if count == 0:
            return

        results = self._collection.get(
            include=["documents", "metadatas"],
            limit=count,
        )

        if results["documents"]:
            for doc_id, doc_text, meta in zip(
                results["ids"], results["documents"], results["metadatas"]
            ):
                tokens = doc_text.lower().split()
                self._bm25_corpus.append(tokens)
                self._chunk_map[doc_id] = TextChunk(
                    chunk_id=doc_id,
                    text=doc_text,
                    metadata=meta or {},
                )

            self._bm25_index = BM25Okapi(self._bm25_corpus)
            logger.info(f"BM25 index rebuilt from {count} existing documents")

    def add_documents(self, chunks: list[TextChunk]) -> int:
        """
        Index a batch of text chunks into both BM25 and ChromaDB.

        Args:
            chunks: List of TextChunk objects to index.

        Returns:
            Number of chunks successfully indexed.
        """
        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        ids = [c.chunk_id for c in chunks]
        metadatas = [c.metadata for c in chunks]

        # Generate embeddings for ChromaDB
        embeddings = embed_texts(texts)

        # Add to ChromaDB (handles deduplication by ID)
        # ChromaDB has a batch size limit, so we chunk the additions
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch_end = min(i + batch_size, len(chunks))
            self._collection.add(
                ids=ids[i:batch_end],
                documents=texts[i:batch_end],
                embeddings=embeddings[i:batch_end].tolist(),
                metadatas=metadatas[i:batch_end],
            )

        # Update BM25 index
        for chunk in chunks:
            tokens = chunk.text.lower().split()
            self._bm25_corpus.append(tokens)
            self._chunk_map[chunk.chunk_id] = chunk

        self._bm25_index = BM25Okapi(self._bm25_corpus)

        logger.info(f"Indexed {len(chunks)} chunks into collection '{self.collection_name}'")
        return len(chunks)

    def _search_bm25(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Perform BM25 lexical search.

        Returns:
            List of (chunk_id, bm25_score) tuples, sorted by score descending.
        """
        if self._bm25_index is None or not self._bm25_corpus:
            return []

        query_tokens = query.lower().split()
        scores = self._bm25_index.get_scores(query_tokens)

        # Map scores back to chunk IDs
        chunk_ids = list(self._chunk_map.keys())
        scored = [(chunk_ids[i], float(scores[i])) for i in range(len(scores)) if i < len(chunk_ids)]
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:top_k]

    def _search_dense(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Perform dense vector search via ChromaDB.

        Returns:
            List of (chunk_id, similarity_score) tuples, sorted by relevance.
        """
        if self._collection.count() == 0:
            return []

        query_embedding = embed_query(query)

        results = self._collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=min(top_k, self._collection.count()),
            include=["distances"],
        )

        scored = []
        if results["ids"] and results["ids"][0]:
            for doc_id, distance in zip(results["ids"][0], results["distances"][0]):
                # ChromaDB returns cosine distance; convert to similarity
                similarity = 1.0 - distance
                scored.append((doc_id, similarity))

        return scored

    def search(
        self,
        query: str,
        top_k: int = 5,
        bm25_weight: float = 0.4,
        dense_weight: float = 0.6,
        rrf_k: int = 60,
    ) -> list[dict]:
        """
        Hybrid search combining BM25 and dense retrieval with RRF.

        Args:
            query: The search query string.
            top_k: Number of final results to return.
            bm25_weight: Weight for BM25 scores in fusion.
            dense_weight: Weight for dense vector scores in fusion.
            rrf_k: RRF constant (higher = more emphasis on lower-ranked results).

        Returns:
            List of result dicts with keys: chunk_id, text, metadata, score.
        """
        # Retrieve candidates from both systems
        bm25_results = self._search_bm25(query, top_k=top_k * 2)
        dense_results = self._search_dense(query, top_k=top_k * 2)

        # Reciprocal Rank Fusion
        rrf_scores: dict[str, float] = {}

        for rank, (chunk_id, _) in enumerate(bm25_results):
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + bm25_weight / (
                rrf_k + rank + 1
            )

        for rank, (chunk_id, _) in enumerate(dense_results):
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + dense_weight / (
                rrf_k + rank + 1
            )

        # Sort by fused RRF score
        sorted_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        # Build result objects
        results = []
        for chunk_id, score in sorted_ids[:top_k]:
            chunk = self._chunk_map.get(chunk_id)
            if chunk:
                results.append(
                    {
                        "chunk_id": chunk_id,
                        "text": chunk.text,
                        "metadata": chunk.metadata,
                        "score": round(score, 4),
                    }
                )
            else:
                # Fallback: fetch from ChromaDB directly
                try:
                    chroma_result = self._collection.get(ids=[chunk_id], include=["documents", "metadatas"])
                    if chroma_result["documents"]:
                        results.append(
                            {
                                "chunk_id": chunk_id,
                                "text": chroma_result["documents"][0],
                                "metadata": chroma_result["metadatas"][0] if chroma_result["metadatas"] else {},
                                "score": round(score, 4),
                            }
                        )
                except Exception:
                    pass

        logger.info(
            f"Hybrid search for '{query[:50]}...' -> {len(results)} results "
            f"(BM25: {len(bm25_results)}, Dense: {len(dense_results)})"
        )
        return results

    def get_document_count(self) -> int:
        """Return the total number of indexed documents."""
        return self._collection.count()

    def delete_collection(self) -> None:
        """Delete the entire collection (useful for testing/reset)."""
        self._chroma_client.delete_collection(self.collection_name)
        self._bm25_corpus = []
        self._bm25_index = None
        self._chunk_map = {}
        logger.warning(f"Deleted collection '{self.collection_name}'")
