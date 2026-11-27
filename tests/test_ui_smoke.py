"""
Streamlit UI End-to-End Smoke & Regression Tests
=================================================
Drives ui/app.py cleanly via streamlit.testing.v1.AppTest against an isolated
FastAPI TestClient + SQLite DB to verify every page and tab renders without
exceptions or regressions from Phases 1-4.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from src.interviewer.ingestion import ingest_questions
from src.interviewer.sources.base_source import RawQuestion

APP_PATH = str(Path(__file__).resolve().parent.parent / "ui" / "app.py")


@pytest.fixture
def ui_env(tmp_path):
    """Isolated SQLite DB, verified user, session token, sample questions, and FastAPI proxy."""
    db_path = str(tmp_path / "test_ui_smoke.db")
    with patch.dict(
        os.environ,
        {
            "SQLITE_DB_PATH": db_path,
            "OTP_MODE": "console",
        },
    ):
        from src.api.main import app
        from src.auth.session_manager import create_session
        from src.utils.checkpoint import _get_connection, create_user, save_user_document

        conn = _get_connection()
        conn.close()

        email = "ui_smoke@example.com"
        create_user(email=email, name="UI Smoke", password="SmokePass123!", is_verified=True)
        token = create_session(email)

        # Seed sample questions across topics for Question Bank & MCQ tests
        ingest_questions([
            RawQuestion(
                question_text="What is the difference between supervised and unsupervised learning?",
                topic="Machine Learning",
                difficulty="easy",
                question_type="technical",
                reference_answer="Supervised uses labeled targets; unsupervised discovers structure in unlabeled data.",
                tags=["ml", "fundamentals"],
            ),
            RawQuestion(
                question_text="How do you reverse a linked list iteratively in O(1) space?",
                topic="Data Structures & Algorithms",
                difficulty="medium",
                question_type="coding",
                reference_answer="Maintain prev, curr, and next pointers while flipping curr.next backward.",
                tags=["linked list"],
            ),
        ])

        client = TestClient(app)

        def _bridge(method: str):
            def _caller(url: str, **kwargs):
                path = url.split("8000", 1)[-1] if "8000" in url else url
                req_kwargs = {}
                for k in ("params", "json", "data", "headers", "files"):
                    if k in kwargs and kwargs[k] is not None:
                        req_kwargs[k] = kwargs[k]
                return client.request(method, path, **req_kwargs)
            return _caller

        with (
            patch.object(requests, "get", side_effect=_bridge("GET")),
            patch.object(requests, "post", side_effect=_bridge("POST")),
            patch.object(requests, "delete", side_effect=_bridge("DELETE")),
        ):
            yield {
                "email": email,
                "token": token,
                "save_user_document": save_user_document,
            }


def test_login_screen_renders_cleanly(ui_env):
    """Unauthenticated landing screen renders with zero exceptions."""
    at = AppTest.from_file(APP_PATH, default_timeout=20)
    at.run()
    assert not at.exception


def test_all_authenticated_pages_and_tabs_render_cleanly(ui_env):
    """Click through all 5 sidebar sections and verify Phase 1-4 UI requirements."""
    email = ui_env["email"]
    token = ui_env["token"]

    # 1) Start without dossier -> check 03 Mock Interview shows Upload Dossier gate
    at = AppTest.from_file(APP_PATH, default_timeout=20)
    at.session_state.session_token = token
    at.session_state.user_email = email
    at.session_state.current_page = "interview"
    at.run()
    assert not at.exception

    all_tabs = [t.label for t in at.tabs]
    assert all_tabs == [
        "01 — AI Audio Interview (Adaptive)",
        "02 — Timed MCQ Examination Battery",
    ]
    assert not any("viva" in lbl.lower() for lbl in all_tabs)

    btn_labels = [b.label for b in at.button]
    assert any("UPLOAD DOSSIER" in lbl.upper() for lbl in btn_labels)

    # 2) Save Resume + JD dossier -> confirm role/company displayed cleanly & old inputs removed
    ui_env["save_user_document"](
        email=email,
        doc_type="resume",
        filename="candidate_resume.pdf",
        content_text="B.Tech CSE candidate skilled in Python, FastAPI, SQL, PyTorch, and Transformers.",
    )
    ui_env["save_user_document"](
        email=email,
        doc_type="jd",
        filename="ml_engineer.pdf",
        content_text="Hiring AI/ML Engineer at Acme Cloud Labs. Requirements: Python, RAG, Transformers.",
        parsed_role="AI/ML Engineer",
        parsed_company="Acme Cloud Labs",
    )

    at = AppTest.from_file(APP_PATH, default_timeout=20)
    at.session_state.session_token = token
    at.session_state.user_email = email
    at.session_state.current_page = "interview"
    at.run()
    assert not at.exception

    text_inputs = [ti.label for ti in at.text_input]
    selectboxes = [sb.label for sb in at.selectbox]
    assert "Target Company" not in selectboxes
    assert "Target Job Role" not in text_inputs
    assert "Focus Round" not in selectboxes
    assert "Interview Type" not in selectboxes
    assert "Interview Round" in selectboxes
    setup_markdowns = "\n".join(m.value for m in at.markdown)
    assert "Interviewing for: AI/ML Engineer @ Acme Cloud Labs (from your dossier)" in setup_markdowns

    # 3) Test active MCQ Battery question rendering with zero raw HTML leakage
    at.session_state.mcq_session = {
        "session_id": "smoke_mcq_1",
        "num_questions": 10,
        "current_idx": 0,
        "correct_count": 0,
    }
    at.session_state.mcq_question_start = 9999999999.0
    at.session_state.mcq_scores = []
    at.session_state.mcq_last_feedback = None
    at.session_state.mcq_current_question = {
        "topic": "Machine Learning",
        "difficulty": "easy",
        "question_text": "<div><span style='color:red'>What is the difference between supervised and unsupervised learning?</span></div>",
        "options": [
            "A. <b>Supervised uses labeled data; unsupervised uses unlabeled data</b>",
            "B. Supervised uses only images",
            "C. Unsupervised always predicts numbers",
            "D. There is no difference",
        ],
    }
    at.run()
    assert not at.exception

    rendered_markdowns = "\n".join(m.value for m in at.markdown)
    rendered_codes = "\n".join(c.value for c in at.code)
    assert "COMPLEXITY: EASY" in rendered_markdowns
    # Ensure the MCQ header block is unindented and contains zero <h3 or leaked tags
    mcq_cards = [m.value for m in at.markdown if "COMPLEXITY: EASY" in m.value]
    assert mcq_cards
    assert all(not card.lstrip().startswith("    ") and "<h3" not in card and "What is the difference" not in card for card in mcq_cards)
    assert not any("What is the difference" in m.value and ("<div" in m.value or "<span" in m.value or "<h3" in m.value) for m in at.markdown)
    assert "</div>" not in rendered_codes
    assert "<span" not in rendered_codes
    assert any(sh.value == "What is the difference between supervised and unsupervised learning?" for sh in at.subheader)
    assert "<b>" not in at.radio[0].options[0]
    assert "Supervised uses labeled data; unsupervised uses unlabeled data" in at.radio[0].options[0]

    # 4) Visit 01 — Upload Dossier, 02 — Curriculum Q&A, 04 — Question Bank, 05 — Diagnostics
    for page_key in ("upload", "chat", "question_bank", "dashboard"):
        at_p = AppTest.from_file(APP_PATH, default_timeout=20)
        at_p.session_state.session_token = token
        at_p.session_state.user_email = email
        at_p.session_state.current_page = page_key
        at_p.run()
        assert not at_p.exception, f"Exception on page {page_key}: {at_p.exception}"

        if page_key == "question_bank":
            qb_tabs = [t.label for t in at_p.tabs]
            assert qb_tabs == [
                "01 — Search & Filter Bank",
                "02 — Browse by Topic",
                "03 — Saved Bookmarks",
                "04 — Import Dataset",
            ]
            qb_selects = [sb.label for sb in at_p.selectbox]
            assert "Company" not in qb_selects
            assert "Category" not in qb_selects
            assert "Platform" not in qb_selects
            assert "Topic" in qb_selects
            assert "Round" in qb_selects
            assert "Difficulty" in qb_selects
            assert "Sort By" in qb_selects

            # JD-first default view prioritizes JD-matched domains ("Machine Learning") over DSA
            scope_radios = [r for r in at_p.radio if r.label == "Domain View"]
            assert len(scope_radios) == 1
            assert scope_radios[0].value == "jd"
            jd_view_md = "\n".join(m.value for m in at_p.markdown)
            assert "supervised and unsupervised learning" in jd_view_md
            assert "reverse a linked list" not in jd_view_md

            # Switching Domain View to "all" reveals questions from all domains with JD first
            scope_radios[0].set_value("all")
            at_p.run()
            assert not at_p.exception
            all_view_md = "\n".join(m.value for m in at_p.markdown)
            assert "supervised and unsupervised learning" in all_view_md
            assert "reverse a linked list" in all_view_md
            assert all_view_md.index("supervised and unsupervised learning") < all_view_md.index("reverse a linked list")

            # Clicking VIEW / Open Questions on a topic card from Tab 2 never raises StreamlitWidgetAlreadyInstantiatedError
            open_btns = [b for b in at_p.button if b.key and b.key.startswith("open_top_")]
            assert open_btns
            open_btns[-1].click().run()
            assert not at_p.exception
            assert "Data Structures & Algorithms" in at_p.session_state.qb_selected_topic or at_p.session_state.qb_selected_topic in (
                "Machine Learning",
                "Data Structures & Algorithms",
            )
        elif page_key == "dashboard":
            dash_text = "\n".join(m.value for m in at_p.markdown)
            assert "viva" not in dash_text.lower()


def test_admin_panel_renders_cleanly(ui_env):
    """Admin portal renders all 6 updated tabs (Materials, Users, Audio+MCQ Results, 11-topic QB, OTP config)."""
    at_admin = AppTest.from_file(APP_PATH, default_timeout=20)
    at_admin.session_state.admin_mode = True
    at_admin.session_state.admin_token = "admin_verified"
    at_admin.run()
    assert not at_admin.exception
    assert not at_admin.error, f"Admin page rendered unexpected error banners: {[e.value for e in at_admin.error]}"

    tab_labels = [t.label for t in at_admin.tabs]
    assert "📊 Assessment Results" in tab_labels
    assert "🌐 Question Bank" in tab_labels
    assert "🔐 Auth & OTP Config" in tab_labels
    assert "🎙️ Adaptive Audio Interviews" in tab_labels
    assert "📝 Timed MCQ Examination Battery" in tab_labels
    assert not any("dynamic question bank" in lbl.lower() or "viva" in lbl.lower() for lbl in tab_labels)

    rendered_md = "\n".join(m.value for m in at_admin.markdown)
    assert "viva" not in rendered_md.lower()
    assert "Centralized Question Bank (11 Curricular Topics)" in rendered_md
    assert "Authentication & Email OTP Configuration" in rendered_md
    assert "CONSOLE" in [m.value for m in at_admin.metric]
