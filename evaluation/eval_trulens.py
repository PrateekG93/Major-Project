"""
TruLens Groundedness Evaluation
=================================
Stub for hallucination detection and groundedness checks.
Uses embedding similarity to verify that generated answers
are supported by the retrieved context.
"""

import json
import os
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


def check_groundedness(
    answer: str,
    context_chunks: list[str],
    threshold: float = 0.5,
) -> dict:
    """
    Check whether a generated answer is grounded in the provided context.

    Uses cosine similarity between the answer embedding and each context chunk.
    If the maximum similarity is below the threshold, the answer is flagged
    as potentially hallucinated.

    Args:
        answer: The generated answer text.
        context_chunks: List of context text strings used for generation.
        threshold: Minimum similarity score to consider the answer grounded.

    Returns:
        Dictionary with 'is_grounded', 'max_similarity', 'avg_similarity', 'details'.
    """
    if not answer or not context_chunks:
        return {
            "is_grounded": False,
            "max_similarity": 0.0,
            "avg_similarity": 0.0,
            "details": "Empty answer or no context provided.",
        }

    from src.rag_assistant.embeddings import embed_query, cosine_similarity

    try:
        answer_emb = embed_query(answer)
        similarities = []

        for i, chunk in enumerate(context_chunks):
            chunk_emb = embed_query(chunk)
            sim = cosine_similarity(answer_emb, chunk_emb)
            similarities.append({
                "chunk_index": i,
                "similarity": round(sim, 4),
                "chunk_preview": chunk[:100] + "..." if len(chunk) > 100 else chunk,
            })

        sim_values = [s["similarity"] for s in similarities]
        max_sim = max(sim_values)
        avg_sim = sum(sim_values) / len(sim_values)

        is_grounded = max_sim >= threshold

        return {
            "is_grounded": is_grounded,
            "max_similarity": round(max_sim, 4),
            "avg_similarity": round(avg_sim, 4),
            "threshold": threshold,
            "verdict": "GROUNDED" if is_grounded else "POTENTIALLY HALLUCINATED",
            "chunk_similarities": similarities,
        }

    except Exception as e:
        logger.error(f"Groundedness check failed: {e}")
        return {
            "is_grounded": False,
            "max_similarity": 0.0,
            "avg_similarity": 0.0,
            "details": f"Error during evaluation: {str(e)}",
        }


def batch_groundedness_check(
    qa_pairs: list[dict],
    output_path: str = "./evaluation/trulens_results.json",
) -> dict:
    """
    Run groundedness checks on a batch of Q&A pairs.

    Args:
        qa_pairs: List of dicts with 'answer' and 'contexts' keys.
        output_path: Path to save results.

    Returns:
        Aggregate statistics dictionary.
    """
    logger.info(f"Running batch groundedness check on {len(qa_pairs)} pairs...")

    results = []
    grounded_count = 0

    for pair in qa_pairs:
        result = check_groundedness(
            answer=pair.get("answer", ""),
            context_chunks=pair.get("contexts", []),
        )
        results.append({
            "question": pair.get("question", ""),
            **result,
        })
        if result["is_grounded"]:
            grounded_count += 1

    total = len(qa_pairs)
    stats = {
        "total_evaluated": total,
        "grounded_count": grounded_count,
        "hallucinated_count": total - grounded_count,
        "groundedness_rate": round(grounded_count / total, 4) if total else 0,
        "detailed_results": results,
    }

    # Save results
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    logger.info(
        f"Groundedness check complete: {grounded_count}/{total} grounded "
        f"({stats['groundedness_rate']*100:.1f}%)"
    )
    return stats


if __name__ == "__main__":
    # Quick test with sample data
    sample_pairs = [
        {
            "question": "What is PCA?",
            "answer": "PCA stands for Principal Component Analysis, a dimensionality reduction technique.",
            "contexts": [
                "Principal Component Analysis (PCA) is an unsupervised technique used to reduce the dimensionality of data while preserving variance."
            ],
        },
        {
            "question": "What is quantum computing?",
            "answer": "Quantum computing uses qubits and superposition to perform calculations.",
            "contexts": [
                "Machine learning is a subset of artificial intelligence."
            ],
        },
    ]

    stats = batch_groundedness_check(sample_pairs)
    print(json.dumps(stats, indent=2))
