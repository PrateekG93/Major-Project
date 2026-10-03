"""
Adaptive Recommendation Engine
================================
Module 4 - ML Scoring (Part 3)

Closes the learning loop:
1. Identifies weak topics from session scores (below threshold)
2. Queries the RAG retriever for relevant notes on weak topics
3. Generates a structured study plan with specific document sections
4. Produces targeted re-test questions for weak areas
"""

import os
from typing import Optional

from dotenv import load_dotenv

from src.ml_scoring.model import get_topic_breakdown
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

WEAKNESS_THRESHOLD = float(os.getenv("WEAKNESS_THRESHOLD", "0.70"))


def identify_weak_topics(
    topic_scores: dict[str, float],
    threshold: float = WEAKNESS_THRESHOLD,
) -> list[dict]:
    """
    Identify topics where the student scored below the threshold.

    Args:
        topic_scores: Dict mapping topic name to percentage score (0-100).
        threshold: Score threshold below which a topic is considered weak (0-1 scale).

    Returns:
        List of weak topic dicts sorted by severity (weakest first).
    """
    threshold_pct = threshold * 100  # Convert to percentage scale

    weak_topics = []
    for topic, score in topic_scores.items():
        if score < threshold_pct:
            severity = "critical" if score < 40 else "moderate" if score < 60 else "mild"
            weak_topics.append({
                "topic": topic,
                "score": score,
                "gap": round(threshold_pct - score, 1),
                "severity": severity,
            })

    # Sort by score ascending (weakest first)
    weak_topics.sort(key=lambda x: x["score"])

    logger.info(
        f"Identified {len(weak_topics)} weak topics "
        f"(threshold={threshold_pct}%): {[w['topic'] for w in weak_topics]}"
    )
    return weak_topics


def generate_study_plan(
    weak_topics: list[dict],
    retrieved_materials: Optional[dict[str, list[dict]]] = None,
) -> list[dict]:
    """
    Generate a structured study plan for weak topics.

    Args:
        weak_topics: List of weak topic dicts from identify_weak_topics().
        retrieved_materials: Optional dict mapping topic -> list of RAG results.

    Returns:
        List of study plan items with topic, priority, and materials.
    """
    plan = []

    for i, weakness in enumerate(weak_topics):
        topic = weakness["topic"]
        severity = weakness["severity"]

        # Determine study priority and estimated time
        if severity == "critical":
            priority = "HIGH"
            estimated_hours = 3
        elif severity == "moderate":
            priority = "MEDIUM"
            estimated_hours = 2
        else:
            priority = "LOW"
            estimated_hours = 1

        # Gather relevant materials from RAG results
        materials = []
        if retrieved_materials and topic in retrieved_materials:
            for chunk in retrieved_materials[topic][:3]:  # Top 3 relevant chunks
                materials.append({
                    "source_doc": chunk.get("metadata", {}).get("source_file", "Unknown"),
                    "section": chunk.get("metadata", {}).get("section", ""),
                    "page": chunk.get("metadata", {}).get("page", ""),
                    "relevance": chunk.get("score", 0),
                    "snippet": chunk.get("text", "")[:200] + "...",
                })

        plan_item = {
            "rank": i + 1,
            "topic": topic,
            "current_score": weakness["score"],
            "target_score": WEAKNESS_THRESHOLD * 100,
            "gap": weakness["gap"],
            "priority": priority,
            "severity": severity,
            "estimated_hours": estimated_hours,
            "recommended_materials": materials,
            "action_items": _generate_action_items(topic, severity),
        }
        plan.append(plan_item)

    logger.info(f"Generated study plan with {len(plan)} items")
    return plan


def generate_retest_topics(
    weak_topics: list[dict],
    num_questions_per_topic: int = 3,
) -> list[dict]:
    """
    Generate targeted retest question specifications for weak areas.

    Args:
        weak_topics: List of weak topic dicts.
        num_questions_per_topic: Number of retest questions per weak topic.

    Returns:
        List of retest specifications with topic, difficulty, and focus areas.
    """
    retest_specs = []

    for weakness in weak_topics:
        topic = weakness["topic"]
        severity = weakness["severity"]

        # Adjust difficulty based on severity
        if severity == "critical":
            difficulties = ["easy", "easy", "medium"]
        elif severity == "moderate":
            difficulties = ["easy", "medium", "medium"]
        else:
            difficulties = ["medium", "medium", "hard"]

        for i, diff in enumerate(difficulties[:num_questions_per_topic]):
            retest_specs.append({
                "topic": topic,
                "difficulty": diff,
                "focus": _get_subtopic_focus(topic),
                "is_retest": True,
                "original_score": weakness["score"],
            })

    logger.info(
        f"Generated {len(retest_specs)} retest question specs "
        f"across {len(weak_topics)} weak topics"
    )
    return retest_specs


def get_full_recommendation(
    session_scores: list[dict],
    retriever=None,
) -> dict:
    """
    Generate a complete recommendation package: topic breakdown,
    weak areas, study plan, and retest specifications.

    Args:
        session_scores: List of answer score dicts with 'topic' and 'score'.
        retriever: Optional HybridRetriever for fetching study materials.

    Returns:
        Complete recommendation dict with all components.
    """
    # Step 1: Compute topic breakdown
    topic_breakdown = get_topic_breakdown(session_scores)

    # Step 2: Identify weak topics
    weak_topics = identify_weak_topics(topic_breakdown)

    # Step 3: Retrieve relevant materials for weak topics (if retriever available)
    retrieved_materials = {}
    if retriever and weak_topics:
        for weakness in weak_topics:
            topic = weakness["topic"]
            try:
                results = retriever.search(
                    f"Key concepts and fundamentals of {topic}",
                    top_k=3,
                )
                retrieved_materials[topic] = results
            except Exception as e:
                logger.warning(f"Could not retrieve materials for {topic}: {e}")

    # Step 4: Generate study plan
    study_plan = generate_study_plan(weak_topics, retrieved_materials)

    # Step 5: Generate retest specs
    retest_specs = generate_retest_topics(weak_topics)

    # Step 6: Overall readiness assessment
    all_scores = list(topic_breakdown.values())
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0

    if avg_score >= 80:
        readiness = "Ready"
        readiness_detail = "Strong performance across most topics. Focus on fine-tuning weak areas."
    elif avg_score >= 65:
        readiness = "Nearly Ready"
        readiness_detail = "Good foundation but some topics need improvement before interviews."
    elif avg_score >= 50:
        readiness = "Needs Work"
        readiness_detail = "Several areas require focused study. Follow the study plan below."
    else:
        readiness = "Not Ready"
        readiness_detail = "Significant gaps detected. Prioritize fundamental concepts in weak topics."

    return {
        "topic_breakdown": topic_breakdown,
        "overall_score": round(avg_score, 1),
        "readiness": readiness,
        "readiness_detail": readiness_detail,
        "weak_topics": weak_topics,
        "study_plan": study_plan,
        "retest_specs": retest_specs,
        "total_estimated_study_hours": sum(
            item["estimated_hours"] for item in study_plan
        ),
    }


def _generate_action_items(topic: str, severity: str) -> list[str]:
    """Generate actionable study steps for a given topic and severity."""
    common_actions = {
        "Python": [
            "Review Python data types, control flow, and OOP concepts",
            "Practice coding problems on LeetCode/HackerRank focusing on Python",
            "Study advanced topics: decorators, generators, context managers",
        ],
        "SQL": [
            "Review JOIN types, GROUP BY, HAVING, and subqueries",
            "Practice window functions (RANK, ROW_NUMBER, LEAD/LAG)",
            "Study query optimization and indexing strategies",
        ],
        "Machine Learning": [
            "Review supervised vs unsupervised learning fundamentals",
            "Study key algorithms: Linear/Logistic Regression, SVM, Random Forest",
            "Practice feature engineering and model evaluation metrics",
        ],
        "Deep Learning": [
            "Review neural network architectures: CNN, RNN, Transformer",
            "Study backpropagation, activation functions, and optimization",
            "Practice implementing models in PyTorch/TensorFlow",
        ],
        "Data Structures & Algorithms": [
            "Review core data structures: arrays, linked lists, trees, graphs",
            "Study algorithm paradigms: divide & conquer, DP, greedy",
            "Practice solving problems with time/space complexity analysis",
        ],
        "System Design": [
            "Study scalability patterns: load balancing, caching, sharding",
            "Practice designing common systems: URL shortener, chat app, feed",
            "Review CAP theorem, consistency models, and microservices",
        ],
        "NLP": [
            "Review text preprocessing: tokenization, stemming, TF-IDF",
            "Study word embeddings (Word2Vec, GloVe) and transformers",
            "Practice with RAG pipelines and LLM integration patterns",
        ],
    }

    actions = common_actions.get(topic, [
        f"Review fundamental concepts of {topic}",
        f"Practice problems related to {topic}",
        f"Study advanced topics in {topic}",
    ])

    if severity == "critical":
        actions.insert(0, f"⚠️ START HERE: Review basic {topic} concepts from your lecture notes")

    return actions


def _get_subtopic_focus(topic: str) -> str:
    """Return a specific subtopic to focus retest questions on."""
    import random
    subtopics = {
        "Python": ["OOP", "Data Structures", "Decorators", "Error Handling", "File I/O"],
        "SQL": ["JOINs", "Window Functions", "Subqueries", "Normalization", "Indexing"],
        "Machine Learning": ["Regression", "Classification", "Clustering", "Evaluation Metrics", "Feature Engineering"],
        "Deep Learning": ["CNNs", "RNNs", "Transformers", "Backpropagation", "Regularization"],
        "Data Structures & Algorithms": ["Trees", "Graphs", "Dynamic Programming", "Sorting", "Hashing"],
        "System Design": ["Caching", "Load Balancing", "Database Design", "API Design", "Microservices"],
        "NLP": ["Tokenization", "Word Embeddings", "Transformers", "RAG", "Text Classification"],
    }
    options = subtopics.get(topic, [topic])
    return random.choice(options)
