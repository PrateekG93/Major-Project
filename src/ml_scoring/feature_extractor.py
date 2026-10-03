"""
Answer Feature Extractor
=========================
Module 4 - ML Scoring (Part 1)

Extracts numerical features from each interview answer for ML scoring:
- Semantic similarity (cosine sim between answer and reference embeddings)
- Response time (seconds, normalized)
- Answer length (word count)
- Keyword coverage (% of expected keywords present)
- Confidence heuristic (vocabulary sophistication)
"""

import re
from typing import Optional

import numpy as np

from src.rag_assistant.embeddings import embed_query, cosine_similarity
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Hedging/uncertainty words that reduce confidence score
HEDGING_WORDS = {
    "maybe", "perhaps", "possibly", "might", "could be", "i think",
    "i guess", "not sure", "i believe", "probably", "somewhat",
    "kind of", "sort of", "i suppose",
}

# Strong/confident language indicators
CONFIDENCE_WORDS = {
    "specifically", "precisely", "exactly", "fundamentally",
    "essentially", "importantly", "significantly", "critically",
    "therefore", "consequently", "furthermore", "moreover",
    "algorithm", "complexity", "implementation", "architecture",
    "optimization", "performance", "scalability",
}


def extract_features(
    answer_text: str,
    reference_answer: str = "",
    response_time: float = 0.0,
    expected_keywords: Optional[list[str]] = None,
) -> dict:
    """
    Extract a feature vector from a candidate's answer.

    Args:
        answer_text: The candidate's answer text.
        reference_answer: The reference/ideal answer for comparison.
        response_time: Time taken to answer in seconds.
        expected_keywords: Optional list of keywords that should appear.

    Returns:
        Dictionary of feature names to float values.
    """
    features = {}

    # --- Feature 1: Semantic Similarity ---
    if reference_answer and answer_text.strip():
        try:
            answer_emb = embed_query(answer_text)
            ref_emb = embed_query(reference_answer)
            features["semantic_similarity"] = cosine_similarity(answer_emb, ref_emb)
        except Exception as e:
            logger.warning(f"Could not compute semantic similarity: {e}")
            features["semantic_similarity"] = 0.0
    else:
        features["semantic_similarity"] = 0.0

    # --- Feature 2: Response Time (normalized) ---
    # Normalize: <10s is very fast, 30-60s is normal, >120s is slow
    features["response_time_raw"] = response_time
    if response_time <= 0:
        features["response_time_score"] = 0.5  # unknown
    elif response_time < 10:
        features["response_time_score"] = 0.9  # very fast
    elif response_time < 30:
        features["response_time_score"] = 0.85
    elif response_time < 60:
        features["response_time_score"] = 0.75
    elif response_time < 120:
        features["response_time_score"] = 0.6
    else:
        features["response_time_score"] = 0.4

    # --- Feature 3: Answer Length ---
    words = answer_text.split()
    features["word_count"] = len(words)
    # Normalized: 20-100 words is ideal; too short or too long is penalized
    if len(words) < 5:
        features["length_score"] = 0.2
    elif len(words) < 15:
        features["length_score"] = 0.5
    elif len(words) < 30:
        features["length_score"] = 0.7
    elif len(words) <= 120:
        features["length_score"] = 1.0
    elif len(words) <= 200:
        features["length_score"] = 0.85
    else:
        features["length_score"] = 0.7  # verbose but still acceptable

    # --- Feature 4: Keyword Coverage ---
    if expected_keywords:
        answer_lower = answer_text.lower()
        matched = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
        features["keyword_coverage"] = matched / len(expected_keywords)
    elif reference_answer:
        # Auto-extract keywords from reference answer
        ref_keywords = _extract_key_terms(reference_answer)
        if ref_keywords:
            answer_lower = answer_text.lower()
            matched = sum(1 for kw in ref_keywords if kw.lower() in answer_lower)
            features["keyword_coverage"] = matched / len(ref_keywords)
        else:
            features["keyword_coverage"] = 0.5
    else:
        features["keyword_coverage"] = 0.5

    # --- Feature 5: Confidence Score ---
    features["confidence_score"] = _compute_confidence(answer_text)

    # --- Feature 6: Completeness (sentence count) ---
    sentences = re.split(r'[.!?]+', answer_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    features["sentence_count"] = len(sentences)
    features["completeness_score"] = min(1.0, len(sentences) / 3.0)

    return features


def features_to_array(features: dict) -> np.ndarray:
    """
    Convert a feature dictionary to a numpy array for ML model input.

    Returns:
        1D numpy array with features in a consistent order.
    """
    feature_order = [
        "semantic_similarity",
        "response_time_score",
        "length_score",
        "keyword_coverage",
        "confidence_score",
        "completeness_score",
    ]
    return np.array([features.get(f, 0.0) for f in feature_order])


def _extract_key_terms(text: str, max_terms: int = 10) -> list[str]:
    """
    Extract key technical terms from reference answer text.
    Simple heuristic: pick capitalized words and multi-word phrases.
    """
    # Remove common stop words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above",
        "below", "between", "same", "than", "too", "very", "just",
        "but", "and", "or", "not", "no", "nor", "if", "then",
        "that", "this", "these", "those", "it", "its", "they",
        "them", "their", "we", "our", "you", "your", "he", "she",
    }

    words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
    key_terms = [
        w for w in words
        if w.lower() not in stop_words
    ]

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for term in key_terms:
        if term.lower() not in seen:
            seen.add(term.lower())
            unique.append(term.lower())

    return unique[:max_terms]


def _compute_confidence(text: str) -> float:
    """
    Compute a confidence heuristic based on language patterns.

    High confidence: uses definitive language, technical terms.
    Low confidence: uses hedging words, uncertainty markers.
    """
    text_lower = text.lower()
    words = text_lower.split()

    if not words:
        return 0.0

    # Count hedging and confidence indicators
    hedge_count = sum(1 for hw in HEDGING_WORDS if hw in text_lower)
    confidence_count = sum(1 for cw in CONFIDENCE_WORDS if cw in text_lower)

    # Base confidence from word count (longer answers tend to be more confident)
    base = min(0.6, len(words) / 50.0)

    # Adjust for hedging and confidence language
    adjustment = (confidence_count * 0.05) - (hedge_count * 0.1)

    score = base + adjustment
    return max(0.0, min(1.0, score))
