"""
RAGAS Evaluation Runner
========================
Evaluates the RAG pipeline on faithfulness, context relevance, and answer relevance
using the RAGAS framework.
"""

import json
import os
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


def create_evaluation_dataset() -> list[dict]:
    """
    Create a test dataset for RAGAS evaluation.
    Each entry has: question, ground_truth, contexts (retrieved), answer (generated).
    """
    return [
        {
            "question": "What is Principal Component Analysis (PCA)?",
            "ground_truth": "PCA is an unsupervised dimensionality reduction technique that finds orthogonal directions of maximum variance in the data by computing eigenvectors of the covariance matrix.",
        },
        {
            "question": "Explain the bias-variance tradeoff.",
            "ground_truth": "Bias is error from oversimplified models (underfitting), variance is error from overly complex models (overfitting). The tradeoff means reducing one often increases the other. The goal is to minimize total error.",
        },
        {
            "question": "What are ACID properties in databases?",
            "ground_truth": "ACID stands for Atomicity (all-or-nothing), Consistency (valid state transitions), Isolation (concurrent transactions don't interfere), and Durability (committed changes survive failures).",
        },
        {
            "question": "How does a hash map handle collisions?",
            "ground_truth": "Hash maps handle collisions via chaining (linked lists at each bucket) or open addressing (probing for the next empty slot using linear, quadratic, or double hashing).",
        },
        {
            "question": "What is the attention mechanism in transformers?",
            "ground_truth": "Attention computes weighted relationships between all positions in a sequence using Query, Key, Value matrices. Self-attention formula: softmax(QK^T/sqrt(d))V. Multi-head attention runs multiple attention functions in parallel.",
        },
    ]


def run_evaluation(
    retriever=None,
    generator_fn=None,
    output_path: str = "./evaluation/ragas_results.json",
) -> dict:
    """
    Run RAGAS evaluation on the RAG pipeline.

    Args:
        retriever: HybridRetriever instance (optional, creates default if None).
        generator_fn: Answer generation function (optional).
        output_path: Path to save evaluation results.

    Returns:
        Dictionary with RAGAS metric scores.
    """
    logger.info("Starting RAGAS evaluation...")

    dataset = create_evaluation_dataset()
    results = []

    for entry in dataset:
        question = entry["question"]
        ground_truth = entry["ground_truth"]

        # Retrieve context
        contexts = []
        if retriever:
            try:
                search_results = retriever.search(question, top_k=3)
                contexts = [r["text"] for r in search_results]
            except Exception as e:
                logger.warning(f"Retrieval failed for '{question}': {e}")

        # Generate answer
        answer = ""
        if generator_fn and contexts:
            try:
                response = generator_fn(
                    query=question,
                    context_chunks=[{"text": c, "metadata": {}, "score": 0} for c in contexts],
                )
                answer = response.get("answer", "")
            except Exception as e:
                logger.warning(f"Generation failed for '{question}': {e}")

        results.append({
            "question": question,
            "ground_truth": ground_truth,
            "contexts": contexts,
            "answer": answer,
        })

    # Compute basic metrics (simplified RAGAS-style metrics)
    metrics = _compute_metrics(results)

    # Save results
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    output = {
        "metrics": metrics,
        "dataset_size": len(dataset),
        "detailed_results": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    logger.info(f"RAGAS evaluation complete. Results saved to {output_path}")
    logger.info(f"Metrics: {metrics}")

    return metrics


def _compute_metrics(results: list[dict]) -> dict:
    """
    Compute simplified evaluation metrics.

    In production, use the full RAGAS library:
        from ragas import evaluate
        from ragas.metrics import faithfulness, context_precision, answer_relevancy
    """
    from src.rag_assistant.embeddings import embed_query, cosine_similarity

    faithfulness_scores = []
    context_relevance_scores = []
    answer_relevance_scores = []

    for result in results:
        question = result["question"]
        answer = result["answer"]
        contexts = result["contexts"]
        ground_truth = result["ground_truth"]

        if not answer:
            continue

        try:
            # Answer relevance: similarity between answer and ground truth
            answer_emb = embed_query(answer)
            gt_emb = embed_query(ground_truth)
            answer_rel = cosine_similarity(answer_emb, gt_emb)
            answer_relevance_scores.append(answer_rel)

            # Context relevance: avg similarity between query and retrieved contexts
            if contexts:
                query_emb = embed_query(question)
                ctx_sims = []
                for ctx in contexts:
                    ctx_emb = embed_query(ctx)
                    ctx_sims.append(cosine_similarity(query_emb, ctx_emb))
                context_relevance_scores.append(sum(ctx_sims) / len(ctx_sims))

            # Faithfulness: similarity between answer and context (is answer grounded?)
            if contexts:
                combined_ctx = " ".join(contexts)
                ctx_combined_emb = embed_query(combined_ctx[:512])
                faith = cosine_similarity(answer_emb, ctx_combined_emb)
                faithfulness_scores.append(faith)

        except Exception as e:
            logger.warning(f"Metric computation failed: {e}")
            continue

    metrics = {}
    if answer_relevance_scores:
        metrics["answer_relevance"] = round(
            sum(answer_relevance_scores) / len(answer_relevance_scores), 4
        )
    if context_relevance_scores:
        metrics["context_relevance"] = round(
            sum(context_relevance_scores) / len(context_relevance_scores), 4
        )
    if faithfulness_scores:
        metrics["faithfulness"] = round(
            sum(faithfulness_scores) / len(faithfulness_scores), 4
        )

    return metrics


if __name__ == "__main__":
    print("Running RAGAS evaluation (standalone mode)...")
    metrics = run_evaluation()
    print(f"\nResults: {json.dumps(metrics, indent=2)}")
