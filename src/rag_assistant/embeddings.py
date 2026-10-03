"""
Embedding Engine
================
Module 2 - RAG Assistant (Part 1)

Wraps sentence-transformers for local embedding generation.
Uses 'all-MiniLM-L6-v2' by default (384-dimensional, runs on CPU).
No external API needed — 100% local and free.
"""

import os
from typing import Optional

import numpy as np
from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

# Lazy-loaded model singleton
_model = None


def _get_model():
    """Lazy-load the sentence-transformer model (downloads on first use)."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info(f"Embedding model loaded successfully (dim={_model.get_sentence_embedding_dimension()})")
    return _model


def embed_texts(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """
    Generate dense vector embeddings for a list of texts.

    Args:
        texts: List of text strings to embed.
        batch_size: Batch size for encoding (affects memory usage).

    Returns:
        NumPy array of shape (len(texts), embedding_dim).
    """
    model = _get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 100,
        normalize_embeddings=True,  # L2 normalize for cosine similarity
    )
    logger.debug(f"Embedded {len(texts)} texts -> shape {embeddings.shape}")
    return np.array(embeddings)


def embed_query(query: str) -> np.ndarray:
    """
    Generate embedding for a single query string.

    Args:
        query: The search query text.

    Returns:
        1D NumPy array of the embedding vector.
    """
    model = _get_model()
    embedding = model.encode(
        query, normalize_embeddings=True
    )
    return np.array(embedding)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.
    Assumes vectors are already L2-normalized.
    """
    return float(np.dot(vec_a, vec_b))


def get_embedding_dimension() -> int:
    """Return the dimensionality of the embedding model."""
    model = _get_model()
    return model.get_sentence_embedding_dimension()
