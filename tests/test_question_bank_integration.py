"""
Tests for Centralized Question Bank, Multi-Level Deduplication & Topic Catalog (Phase 4)
========================================================================================
Tests:
- Exact, normalized, lexical, and semantic embedding deduplication
- Search, filtering (Topic, Round, Difficulty), sorting, pagination, topic catalog, bookmarks
- JSON/CSV dataset import and taxonomy integrity
"""

import os
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.interviewer.ingestion import ingest_questions
from src.interviewer.sources.base_source import RawQuestion
from src.interviewer.sources.classifier import FIXED_TOPICS


@pytest.fixture
def qb_env(tmp_path):
    """Isolated DB with verified user session for Question Bank tests."""
    db_path = str(tmp_path / "test_qb.db")
    with patch.dict(
        os.environ,
        {"SQLITE_DB_PATH": db_path, "OTP_MODE": "console"},
    ):
        from src.utils.checkpoint import _get_connection, create_user
        from src.auth.session_manager import create_session

        conn = _get_connection()
        conn.close()

        create_user("QB Tester", "qb@jklu.edu.in", "Password123", is_verified=True)
        token = create_session("qb@jklu.edu.in")
        yield db_path, token


def test_multilevel_deduplication_exact_lexical_and_semantic(qb_env):
    """
    Verify exact, lexical, and semantic duplicate detection logs duplicate relationships
    while preserving legitimate distinct questions.
    """
    db_path, _ = qb_env

    q_orig = RawQuestion(
        question_text="What is the difference between a process and a thread in operating systems?",
        interview_round="Technical",
        topic="Operating Systems",
    )
    q_norm = RawQuestion(
        question_text="Q1. what is the difference between a process and a thread in operating systems",
        interview_round="Technical",
        topic="Operating Systems",
    )
    q_semantic = RawQuestion(
        question_text="Explain how a thread differs from a process inside an operating system.",
        interview_round="Technical",
        topic="Operating Systems",
    )
    q_distinct = RawQuestion(
        question_text="How does virtual memory paging work and what causes a page fault?",
        interview_round="Technical",
        topic="Operating Systems",
        difficulty="hard",
    )

    stats = ingest_questions([q_orig, q_norm, q_semantic, q_distinct], enable_semantic_dedup=True)
    assert stats["new_canonical"] == 2
    assert (stats["duplicate_exact"] + stats["duplicate_lexical"] + stats["duplicate_semantic"]) == 2

    conn = sqlite3.connect(db_path)
    freq = conn.execute("SELECT frequency FROM canonical_questions ORDER BY id ASC LIMIT 1").fetchone()[0]
    assert freq == 3
    cols = [r[1] for r in conn.execute("PRAGMA table_info(canonical_questions)").fetchall()]
    assert "category" not in cols
    conn.close()


def test_search_filter_sort_pagination_topics_and_bookmarks(qb_env):
    db_path, token = qb_env
    from src.api.main import app
    client = TestClient(app)

    sample = [
        RawQuestion(
            question_text="Explain two-pointer techniques for sorted array problems.",
            topic="Data Structures & Algorithms",
            difficulty="easy",
            interview_round="Coding",
            reference_answer="Two pointers scan inward or fast/slow to cut O(n^2) loops to O(n).",
            tags=["arrays", "two pointers"],
        ),
        RawQuestion(
            question_text="How does B+Tree indexing speed up range queries in SQL?",
            topic="SQL & Databases",
            difficulty="medium",
            interview_round="Technical",
            reference_answer="B+Tree stores keys sorted in linked leaf nodes enabling sequential range scans.",
            tags=["sql", "indexing"],
        ),
        RawQuestion(
            question_text="Describe a time you resolved a technical disagreement within your team.",
            topic="Behavioral & HR",
            difficulty="easy",
            interview_round="HR",
            is_technical=False,
            reference_answer="Focus on active listening, objective benchmarks, and shared goals using STAR.",
            tags=["conflict", "teamwork"],
        ),
    ]
    ingest_questions(sample, enable_semantic_dedup=False)

    # Search by topic and round
    r1 = client.get(
        "/api/v1/questions/search",
        params={"topic": "Data Structures & Algorithms", "interview_round": "Coding", "page": 1, "page_size": 5},
        headers={"x-session-token": token},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["total"] == 1
    assert d1["items"][0]["topic"] == "Data Structures & Algorithms"
    assert "company" not in d1["items"][0]
    assert "category" not in d1["items"][0]

    # Filter HR questions
    r_hr = client.get(
        "/api/v1/questions/search",
        params={"interview_round": "HR", "page": 1, "page_size": 10},
        headers={"x-session-token": token},
    )
    assert r_hr.status_code == 200
    assert r_hr.json()["total"] == 1
    assert r_hr.json()["items"][0]["is_technical"] is False

    # Bookmark & verify
    first_id = d1["items"][0]["id"]
    bm_post = client.post(
        f"/api/v1/questions/{first_id}/bookmark",
        json={"notes": "Review binary search variant"},
        headers={"x-session-token": token},
    )
    assert bm_post.status_code == 200

    bm_get = client.get("/api/v1/questions/bookmarks", headers={"x-session-token": token})
    assert bm_get.status_code == 200
    assert any(item["id"] == first_id for item in bm_get.json()["items"])

    bm_del = client.delete(f"/api/v1/questions/{first_id}/bookmark", headers={"x-session-token": token})
    assert bm_del.status_code == 200

    # Import CSV dataset
    csv_payload = (
        "question_text,topic,interview_round,difficulty,reference_answer\n"
        '"Explain how consistent hashing minimizes key remapping.",System Design,Technical,hard,Only k/N keys move when a node joins or leaves.\n'
    )
    imp_res = client.post(
        "/api/v1/questions/import",
        json={"format": "csv", "content": csv_payload},
        headers={"x-session-token": token},
    )
    assert imp_res.status_code == 200
    assert imp_res.json()["stats"]["new_canonical"] == 1

    # Topics catalog endpoint
    top_res = client.get("/api/v1/questions/topics")
    assert top_res.status_code == 200
    topics = top_res.json()["topics"]
    assert any(t["topic"] == "System Design" and t["hard_count"] >= 1 for t in topics)

    # Facets endpoint contains topics, rounds, difficulties, and optional jd_context
    fac_res = client.get("/api/v1/questions/filters")
    assert fac_res.status_code == 200
    fac = fac_res.json()
    assert set(fac.keys()) == {"topics", "rounds", "difficulties", "jd_context"}
    assert len(FIXED_TOPICS) == 11
