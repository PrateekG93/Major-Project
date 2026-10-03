"""
Tests for ML Scoring Module
==============================
Tests feature extraction, model training/prediction, and recommendation engine.
"""

import pytest
import numpy as np


class TestFeatureExtractor:
    """Tests for answer feature extraction."""

    def test_extract_features_basic(self):
        """Test basic feature extraction from an answer."""
        from src.ml_scoring.feature_extractor import extract_features

        features = extract_features(
            answer_text="PCA is a dimensionality reduction technique that finds principal components.",
            reference_answer="PCA reduces dimensions by finding orthogonal components of maximum variance.",
            response_time=25.0,
        )

        assert "semantic_similarity" in features
        assert "response_time_score" in features
        assert "length_score" in features
        assert "keyword_coverage" in features
        assert "confidence_score" in features
        assert "completeness_score" in features

        # Check ranges
        assert 0 <= features["semantic_similarity"] <= 1
        assert 0 <= features["confidence_score"] <= 1

    def test_empty_answer_features(self):
        """Test feature extraction from an empty answer."""
        from src.ml_scoring.feature_extractor import extract_features

        features = extract_features(answer_text="", reference_answer="Some reference.")

        assert features["semantic_similarity"] == 0.0
        assert features["word_count"] == 0

    def test_features_to_array(self):
        """Test converting features dict to numpy array."""
        from src.ml_scoring.feature_extractor import extract_features, features_to_array

        features = extract_features(
            answer_text="This is a test answer with some technical content.",
            response_time=30.0,
        )
        array = features_to_array(features)

        assert isinstance(array, np.ndarray)
        assert len(array) == 6

    def test_fast_response_gets_high_time_score(self):
        """Test that fast responses get higher time scores."""
        from src.ml_scoring.feature_extractor import extract_features

        fast = extract_features("answer", response_time=5.0)
        slow = extract_features("answer", response_time=150.0)

        assert fast["response_time_score"] > slow["response_time_score"]


class TestMLModel:
    """Tests for the ML scoring model."""

    def test_train_model(self):
        """Test model training completes successfully."""
        from src.ml_scoring.model import train_model

        metrics = train_model(force_retrain=True)

        assert metrics["status"] == "trained"
        assert "rmse" in metrics
        assert "r2_score" in metrics
        assert metrics["rmse"] < 0.2  # Reasonable RMSE on synthetic data

    def test_predict_score(self):
        """Test score prediction returns valid output."""
        from src.ml_scoring.model import predict_score

        result = predict_score(
            answer_text="Machine learning uses algorithms to learn patterns from data.",
            reference_answer="Machine learning is a field of AI that enables systems to learn from data.",
            response_time=20.0,
        )

        assert "score" in result
        assert "grade" in result
        assert 0 <= result["score"] <= 1
        assert result["grade"] in ["Excellent", "Good", "Average", "Below Average", "Needs Improvement"]

    def test_topic_breakdown(self):
        """Test per-topic score aggregation."""
        from src.ml_scoring.model import get_topic_breakdown

        scores = [
            {"topic": "Python", "score": 0.8},
            {"topic": "Python", "score": 0.9},
            {"topic": "SQL", "score": 0.5},
            {"topic": "SQL", "score": 0.6},
        ]

        breakdown = get_topic_breakdown(scores)

        assert "Python" in breakdown
        assert "SQL" in breakdown
        assert breakdown["Python"] > breakdown["SQL"]


class TestRecommendationEngine:
    """Tests for the adaptive recommendation engine."""

    def test_identify_weak_topics(self):
        """Test weak topic identification."""
        from src.ml_scoring.recommendation_engine import identify_weak_topics

        scores = {"Python": 82.0, "SQL": 55.0, "ML": 40.0, "DSA": 75.0}
        weak = identify_weak_topics(scores, threshold=0.70)

        topic_names = [w["topic"] for w in weak]
        assert "SQL" in topic_names
        assert "ML" in topic_names
        assert "Python" not in topic_names  # Above threshold

    def test_generate_study_plan(self):
        """Test study plan generation."""
        from src.ml_scoring.recommendation_engine import (
            identify_weak_topics,
            generate_study_plan,
        )

        scores = {"Python": 82.0, "SQL": 55.0, "ML": 40.0}
        weak = identify_weak_topics(scores)
        plan = generate_study_plan(weak)

        assert len(plan) > 0
        assert all("topic" in item for item in plan)
        assert all("priority" in item for item in plan)
        assert all("action_items" in item for item in plan)

    def test_full_recommendation(self):
        """Test the complete recommendation pipeline."""
        from src.ml_scoring.recommendation_engine import get_full_recommendation

        session_scores = [
            {"topic": "Python", "score": 0.85},
            {"topic": "SQL", "score": 0.50},
            {"topic": "ML", "score": 0.35},
        ]

        result = get_full_recommendation(session_scores)

        assert "topic_breakdown" in result
        assert "overall_score" in result
        assert "readiness" in result
        assert "weak_topics" in result
        assert "study_plan" in result
