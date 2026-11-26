"""
Tests for Ingestion Pipeline & Deduplication
============================================
Tests normalization, fingerprinting, near-duplicate detection,
validation, and idempotent database ingestion.
"""

import os
import sqlite3
import pytest
from unittest.mock import patch

from src.interviewer.sources.base_source import RawQuestion
from src.interviewer.ingestion import (
    normalize_text,
    compute_fingerprint,
    is_near_duplicate,
    validate_question,
    ingest_questions,
    seed_curated_questions,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create an isolated temporary SQLite database for testing."""
    db_file = str(tmp_path / "test_copilot.db")
    with patch.dict(os.environ, {"SQLITE_DB_PATH": db_file}):
        from src.utils.checkpoint import _get_connection
        conn = _get_connection()
        conn.close()
        yield db_file


def test_normalize_text():
    assert normalize_text("Q1. What is Python?") == "what is python"
    assert normalize_text("Question 2: What is GIL?") == "what is gil"
    assert normalize_text("  Explain decorators in Python...  ") == "explain decorators in python"
    assert normalize_text("What   is    a    closure?") == "what is a closure"


def test_compute_fingerprint():
    fp1 = compute_fingerprint("what is the difference between a list and a tuple")
    fp2 = compute_fingerprint("what is the difference between a list and a tuple")
    assert fp1 == fp2
    assert len(fp1) == 64

    fp3 = compute_fingerprint("explain python gil")
    assert fp1 != fp3


def test_is_near_duplicate():
    text1 = "what is the difference between list and tuple in python"
    text2 = "what is the difference between lists and tuples in python"
    text3 = "explain convolutional neural networks for computer vision"

    assert is_near_duplicate(text1, text2, threshold=0.85) is True
    assert is_near_duplicate(text1, text3, threshold=0.85) is False


def test_validate_question():
    valid_q = RawQuestion(
        question_text="Explain the concept of database indexing in SQL.",
        topic="SQL & Databases",
    )
    assert validate_question(valid_q) is True

    short_q = RawQuestion(question_text="Why?")
    assert validate_question(short_q) is False

    word_q = RawQuestion(question_text="Inheritance")
    assert validate_question(word_q) is False

    punct_q = RawQuestion(question_text="??????????")
    assert validate_question(punct_q) is False


def test_ingest_questions_exact_dedup(temp_db):
    """Test that identical questions across two rounds link to the same canonical question."""
    q1 = RawQuestion(
        question_text="What is the difference between list and tuple in Python?",
        source_url="https://example.com/q1",
        interview_round="Technical",
        topic="Python",
    )
    q2 = RawQuestion(
        question_text="What is the difference between list and tuple in Python?",
        source_url="https://example.com/q2",
        interview_round="Coding",
        topic="Python",
    )

    stats = ingest_questions([q1, q2])

    assert stats["total_input"] == 2
    assert stats["valid"] == 2
    assert stats["new_canonical"] == 1
    assert stats["duplicate_exact"] == 1
    assert stats["sources_added"] == 2

    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM canonical_questions")
    assert cur.fetchone()[0] == 1

    cur.execute("SELECT COUNT(*) FROM question_sources")
    assert cur.fetchone()[0] == 2

    cur.execute("SELECT interview_round FROM question_sources ORDER BY interview_round")
    rounds = [r[0] for r in cur.fetchall()]
    assert rounds == ["Coding", "Technical"]
    conn.close()


def test_seed_curated_questions(temp_db):
    """Test seeding curated questions into canonical DB idempotently."""
    sample_curated = [
        {
            "id": "py_001",
            "topic": "Python",
            "round": "Technical",
            "difficulty": "easy",
            "question_text": "What is the difference between a list and a tuple in Python?",
            "reference_answer": "Lists are mutable, tuples are immutable.",
        },
        {
            "id": "py_002",
            "topic": "Python",
            "round": "Technical",
            "difficulty": "easy",
            "question_text": "Explain the difference between '==' and 'is' operators in Python.",
            "reference_answer": "== checks value equality, is checks object identity.",
        },
    ]

    stats = seed_curated_questions(sample_curated)
    assert stats["new_canonical"] == 2
    assert stats["sources_added"] == 2

    stats2 = seed_curated_questions(sample_curated)
    assert stats2["new_canonical"] == 0
    assert stats2["duplicate_exact"] == 2
