"""
ML Scoring Model
=================
Module 4 - ML Scoring (Part 2)

Trains and serves RandomForest + XGBoost models for answer quality prediction.
Ships a pre-generated synthetic training set and can train/load models on demand.
"""

import os
import json
from typing import Optional

import numpy as np
import joblib
from dotenv import load_dotenv

from src.ml_scoring.feature_extractor import extract_features, features_to_array
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

MODEL_PATH = os.getenv("SCORING_MODEL_PATH", "./models/scoring_model.joblib")


def _generate_training_data(n_samples: int = 500) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic training data for the scoring model.

    Creates realistic feature vectors representing answers of varying quality.
    Features: [semantic_sim, time_score, length_score, keyword_cov, confidence, completeness]

    Returns:
        (X, y) where X is features array and y is quality scores (0-1).
    """
    np.random.seed(42)

    X = np.zeros((n_samples, 6))
    y = np.zeros(n_samples)

    for i in range(n_samples):
        # Generate answers of different quality tiers
        tier = np.random.choice(["excellent", "good", "average", "poor", "bad"],
                                p=[0.15, 0.25, 0.30, 0.20, 0.10])

        if tier == "excellent":
            X[i] = [
                np.random.uniform(0.80, 0.98),  # semantic_sim
                np.random.uniform(0.70, 0.95),  # time_score
                np.random.uniform(0.80, 1.00),  # length_score
                np.random.uniform(0.75, 1.00),  # keyword_coverage
                np.random.uniform(0.70, 1.00),  # confidence
                np.random.uniform(0.80, 1.00),  # completeness
            ]
            y[i] = np.random.uniform(0.85, 1.00)

        elif tier == "good":
            X[i] = [
                np.random.uniform(0.60, 0.85),
                np.random.uniform(0.60, 0.90),
                np.random.uniform(0.65, 0.95),
                np.random.uniform(0.55, 0.80),
                np.random.uniform(0.55, 0.85),
                np.random.uniform(0.60, 0.90),
            ]
            y[i] = np.random.uniform(0.70, 0.88)

        elif tier == "average":
            X[i] = [
                np.random.uniform(0.35, 0.65),
                np.random.uniform(0.40, 0.80),
                np.random.uniform(0.40, 0.75),
                np.random.uniform(0.30, 0.60),
                np.random.uniform(0.35, 0.65),
                np.random.uniform(0.35, 0.70),
            ]
            y[i] = np.random.uniform(0.45, 0.72)

        elif tier == "poor":
            X[i] = [
                np.random.uniform(0.15, 0.40),
                np.random.uniform(0.30, 0.65),
                np.random.uniform(0.20, 0.55),
                np.random.uniform(0.10, 0.35),
                np.random.uniform(0.15, 0.45),
                np.random.uniform(0.15, 0.50),
            ]
            y[i] = np.random.uniform(0.25, 0.48)

        else:  # bad
            X[i] = [
                np.random.uniform(0.00, 0.20),
                np.random.uniform(0.20, 0.50),
                np.random.uniform(0.10, 0.30),
                np.random.uniform(0.00, 0.15),
                np.random.uniform(0.00, 0.25),
                np.random.uniform(0.00, 0.25),
            ]
            y[i] = np.random.uniform(0.05, 0.28)

        # Add small noise
        X[i] += np.random.normal(0, 0.02, 6)
        X[i] = np.clip(X[i], 0, 1)
        y[i] = np.clip(y[i], 0, 1)

    return X, y


def train_model(force_retrain: bool = False) -> dict:
    """
    Train the scoring model ensemble (RandomForest + XGBoost).

    Args:
        force_retrain: If True, retrain even if a saved model exists.

    Returns:
        Dictionary with training metrics (RMSE, R², MAE).
    """
    if os.path.exists(MODEL_PATH) and not force_retrain:
        logger.info(f"Model already exists at {MODEL_PATH}. Use force_retrain=True to retrain.")
        return {"status": "already_trained", "model_path": MODEL_PATH}

    from sklearn.ensemble import RandomForestRegressor, VotingRegressor
    from sklearn.model_selection import cross_val_score
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

    try:
        from xgboost import XGBRegressor
        has_xgboost = True
    except ImportError:
        has_xgboost = False
        logger.warning("XGBoost not available, using RandomForest only")

    logger.info("Training scoring model...")

    X, y = _generate_training_data(n_samples=500)

    # Split for evaluation
    split_idx = int(0.8 * len(X))
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # Build ensemble
    rf = RandomForestRegressor(
        n_estimators=100,
        max_depth=8,
        min_samples_leaf=5,
        random_state=42,
    )

    if has_xgboost:
        xgb = XGBRegressor(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
            verbosity=0,
        )
        model = VotingRegressor(
            estimators=[("rf", rf), ("xgb", xgb)],
        )
    else:
        model = rf

    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    mae = float(mean_absolute_error(y_test, y_pred))
    r2 = float(r2_score(y_test, y_pred))

    # Save model
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)

    metrics = {
        "status": "trained",
        "model_path": MODEL_PATH,
        "rmse": round(rmse, 4),
        "mae": round(mae, 4),
        "r2_score": round(r2, 4),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "has_xgboost": has_xgboost,
    }

    logger.info(f"Model trained: RMSE={rmse:.4f}, R²={r2:.4f}, MAE={mae:.4f}")
    return metrics


def _load_model():
    """Load the trained model, training if necessary."""
    if not os.path.exists(MODEL_PATH):
        logger.info("No trained model found. Training now...")
        train_model()

    return joblib.load(MODEL_PATH)


def predict_score(
    answer_text: str,
    reference_answer: str = "",
    response_time: float = 0.0,
    expected_keywords: Optional[list[str]] = None,
) -> dict:
    """
    Predict the quality score for a single answer.

    Args:
        answer_text: The candidate's answer.
        reference_answer: The ideal/reference answer.
        response_time: Time taken in seconds.
        expected_keywords: Expected keywords to check coverage.

    Returns:
        Dict with 'score' (0-1), 'features', and 'grade'.
    """
    # Extract features
    features = extract_features(
        answer_text, reference_answer, response_time, expected_keywords
    )

    # Convert to array
    feature_array = features_to_array(features).reshape(1, -1)

    # Predict
    model = _load_model()
    score = float(model.predict(feature_array)[0])
    score = max(0.0, min(1.0, score))

    # Determine grade
    if score >= 0.85:
        grade = "Excellent"
    elif score >= 0.70:
        grade = "Good"
    elif score >= 0.50:
        grade = "Average"
    elif score >= 0.30:
        grade = "Below Average"
    else:
        grade = "Needs Improvement"

    return {
        "score": round(score, 3),
        "grade": grade,
        "features": features,
    }


def get_topic_breakdown(session_scores: list[dict]) -> dict:
    """
    Aggregate individual answer scores into per-topic performance breakdown.

    Args:
        session_scores: List of dicts with 'topic' and 'score' keys.

    Returns:
        Dict mapping topic names to average percentage scores.
    """
    topic_scores: dict[str, list[float]] = {}

    for entry in session_scores:
        topic = entry.get("topic", "General")
        score = entry.get("score", 0.0)
        if topic not in topic_scores:
            topic_scores[topic] = []
        topic_scores[topic].append(score)

    return {
        topic: round(np.mean(scores) * 100, 1)
        for topic, scores in topic_scores.items()
    }
