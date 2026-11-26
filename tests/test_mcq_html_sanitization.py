"""
Tests for MCQ HTML Sanitization & Clean Rendering (Phase 3)
=========================================================
Ensures no stored MCQ question, option, explanation, or canonical question
contains '<' followed by an HTML tag name, and that dirty HTML inputs are stripped
before DB storage and rendering.
"""

import json
import os
import sqlite3
from unittest.mock import patch

import pytest

from src.utils.text_utils import contains_html_tag, strip_html_markup


def test_strip_html_markup_removes_tags_and_inline_styles():
    dirty = (
        '<div style="color:red"><span>COMPLEXITY: EASY</span></div>\n'
        '<h3 style="font-family: var(--font-sans);">What is the difference between supervised and unsupervised learning?</h3>'
    )
    cleaned = strip_html_markup(dirty)
    assert not contains_html_tag(cleaned)
    assert "<div" not in cleaned
    assert "<span" not in cleaned
    assert "<h3" not in cleaned
    assert "What is the difference between supervised and unsupervised learning?" in cleaned


def test_mcq_db_storage_strips_html_tags(tmp_path):
    """Fail if any MCQ question or option stored in DB contains '<' followed by a tag name."""
    db_file = str(tmp_path / "test_mcq_sanitize.db")
    with patch.dict(os.environ, {"SQLITE_DB_PATH": db_file}):
        from src.utils.checkpoint import (
            _get_connection,
            create_user,
            save_mcq_answer,
            save_mcq_session,
        )

        conn = _get_connection()
        conn.close()

        create_user("Sanitize User", "clean@jklu.edu.in", "Password123", is_verified=True)

        dirty_q = '<div style="margin:0"><h3 style="color:red">What is overfitting?</h3></div>'
        dirty_opts = [
            "<span>A. Fitting noise too closely</span>",
            "<b>B. Low variance</b>",
            "C. High bias",
            "<i>D. Under-training</i>",
        ]
        dirty_expl = "<p>Overfitting occurs when a model memorizes training noise.</p>"

        save_mcq_session(
            "mcq_clean_01",
            "clean@jklu.edu.in",
            1,
            {
                "questions": [
                    {
                        "question_text": dirty_q,
                        "options": dirty_opts,
                        "correct_answer": "A",
                        "explanation": dirty_expl,
                        "topic": "Machine Learning",
                        "difficulty": "easy",
                    }
                ],
                "current_index": 0,
                "answers": [],
                "total_correct": 0,
            },
        )
        save_mcq_answer(
            session_id="mcq_clean_01",
            question_index=0,
            question_text=dirty_q,
            options=dirty_opts,
            correct_answer="A",
            user_answer="A",
            is_correct=True,
            is_timeout=False,
            response_time=4.0,
            topic="Machine Learning",
            explanation=dirty_expl,
        )

        # Verify zero '<' + tag name exists in DB
        c = sqlite3.connect(db_file)
        for q_text, opts_json, expl in c.execute(
            "SELECT question_text, options_json, explanation FROM mcq_answers"
        ).fetchall():
            assert not contains_html_tag(q_text), f"HTML tag found in mcq_answers.question_text: {q_text}"
            assert not contains_html_tag(expl), f"HTML tag found in mcq_answers.explanation: {expl}"
            for opt in json.loads(opts_json):
                assert not contains_html_tag(opt), f"HTML tag found in mcq_answers option: {opt}"

        for (state_json,) in c.execute("SELECT state_json FROM mcq_sessions").fetchall():
            st_obj = json.loads(state_json)
            for q in st_obj.get("questions", []):
                assert not contains_html_tag(q.get("question_text", ""))
                assert not contains_html_tag(q.get("explanation", ""))
                for opt in q.get("options", []):
                    assert not contains_html_tag(opt)
        c.close()


def test_production_db_has_no_html_tags_in_questions_or_options():
    """Fail if the active SQLite database contains '<' followed by a tag name in MCQ or bank rows."""
    db_path = os.getenv("SQLITE_DB_PATH", "./data/copilot_app.db")
    if not os.path.exists(db_path):
        pytest.skip("Production DB not created yet")

    conn = sqlite3.connect(db_path)
    try:
        # Check mcq_answers
        for q_text, opts_json in conn.execute("SELECT question_text, options_json FROM mcq_answers").fetchall():
            assert not contains_html_tag(q_text), f"Dirty HTML in mcq_answers: {q_text}"
            for opt in json.loads(opts_json or "[]"):
                assert not contains_html_tag(opt), f"Dirty HTML in mcq_answers option: {opt}"

        # Check mcq_sessions state_json
        for (state_json,) in conn.execute("SELECT state_json FROM mcq_sessions").fetchall():
            st_obj = json.loads(state_json or "{}")
            for q in st_obj.get("questions", []):
                assert not contains_html_tag(q.get("question_text", "")), f"Dirty HTML in mcq_sessions: {q}"
                for opt in q.get("options", []):
                    assert not contains_html_tag(opt), f"Dirty HTML in mcq_sessions option: {opt}"

        # Check canonical_questions
        for (q_text,) in conn.execute("SELECT question_text FROM canonical_questions").fetchall():
            assert not contains_html_tag(q_text), f"Dirty HTML in canonical_questions: {q_text}"
    finally:
        conn.close()
