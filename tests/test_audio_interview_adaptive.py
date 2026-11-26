"""
Comprehensive Tests for BeFluent-Inspired Adaptive Audio Interview System (Task 2)
====================================================================================
Tests:
- Audio validation, retention cleanup, deterministic fluency metrics
- Adaptive Interview Scenarios 1–5 (incomplete, incorrect, excellent, irrelevant, short)
- Question Bank -> Audio Interview integration
- Session persistence, resume, ownership isolation, final report, and full E2E integration flow
"""

import io
import json
import os
import struct
import time
import wave
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.interviewer.audio_service import (
    cleanup_expired_audio,
    compute_fluency_metrics,
    save_audio_upload,
)
from src.interviewer.ingestion import ingest_questions
from src.interviewer.sources.base_source import RawQuestion


def _make_dummy_wav_bytes(duration_sec: float = 1.5, sample_rate: int = 16000) -> bytes:
    """Generate a valid in-memory WAV audio file for upload testing."""
    buf = io.BytesIO()
    n_samples = int(duration_sec * sample_rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * n_samples, *([120] * n_samples)))
    return buf.getvalue()


@pytest.fixture
def audio_env(tmp_path):
    """Isolated SQLite DB, audio dir, and two verified users for isolation & flow tests."""
    db_path = str(tmp_path / "test_audio.db")
    aud_dir = str(tmp_path / "audio_recordings")
    with patch.dict(
        os.environ,
        {
            "SQLITE_DB_PATH": db_path,
            "AUDIO_STORAGE_DIR": aud_dir,
            "OTP_MODE": "console",
        },
    ):
        from src.utils.checkpoint import _get_connection, create_user
        from src.auth.session_manager import create_session

        conn = _get_connection()
        conn.close()

        # Seed Question Bank & Candidate Dossier
        sample_bank = [
            RawQuestion(
                question_text="Explain how you would design a scalable distributed cache across multiple nodes.",
                topic="System Design",
                difficulty="hard",
                interview_round="Technical",
                reference_answer="Use consistent hashing, LRU eviction per node, replication, and TTL expiration.",
            ),
            RawQuestion(
                question_text="Explain database normalization across 1NF, 2NF, 3NF, and BCNF.",
                topic="SQL & Databases",
                difficulty="medium",
                interview_round="Technical",
                reference_answer="1NF removes repeating groups; 2NF partial dependencies; 3NF transitive; BCNF superkey determinants.",
            ),
            RawQuestion(
                question_text="How do Python generators differ from regular functions?",
                topic="Python",
                difficulty="medium",
                interview_round="Technical",
                reference_answer="Generators yield values lazily while preserving execution state across iterations.",
            ),
        ]
        ingest_questions(sample_bank, enable_semantic_dedup=False)

        create_user("User One", "u1@jklu.edu.in", "Password123", is_verified=True)
        create_user("User Two", "u2@jklu.edu.in", "Password123", is_verified=True)
        from src.utils.checkpoint import save_user_document
        save_user_document(
            "u1@jklu.edu.in",
            "resume",
            "Experienced Python and DBMS Software Development Engineer with Redis, FastAPI, and SQL expertise.",
            "resume.pdf",
        )
        save_user_document(
            "u1@jklu.edu.in",
            "jd",
            "Job Title: Software Development Engineer\nCompany: Acme Cloud\nSkills: Python, SQL, System Design, Caching.",
            "jd.pdf",
            parsed_role="Software Development Engineer",
            parsed_company="Acme Cloud",
        )
        tok1 = create_session("u1@jklu.edu.in")
        tok2 = create_session("u2@jklu.edu.in")
        yield db_path, aud_dir, tok1, tok2


def test_audio_validation_fluency_and_retention(audio_env):
    _, aud_dir, _, _ = audio_env

    # Reject unsupported format
    with pytest.raises(ValueError, match="Unsupported audio format"):
        save_audio_upload("sess_1", 0, "clip.txt", b"x" * 2000)

    # Reject empty audio
    with pytest.raises(ValueError, match="empty or too short"):
        save_audio_upload("sess_1", 0, "clip.wav", b"123")

    # Save valid audio and test retention cleanup
    wav_bytes = _make_dummy_wav_bytes()
    saved_path = save_audio_upload("sess_1", 0, "clip.wav", wav_bytes)
    assert os.path.exists(saved_path)

    # Age the file beyond retention window and verify cleanup
    old_ts = time.time() - (48 * 3600)
    os.utime(saved_path, (old_ts, old_ts))
    removed = cleanup_expired_audio()
    assert removed >= 1
    assert not os.path.exists(saved_path)

    # Fluency metrics (BeFluent deterministic WPM & filler counter)
    flu = compute_fluency_metrics(
        "Um, normalization is basically organizing tables to avoid, you know, redundancy.",
        duration_seconds=30.0,
    )
    assert flu["filler_word_count"] == 3  # um, basically, you know
    assert flu["words_per_minute"] > 0


@pytest.mark.parametrize(
    "scenario_name,transcript,mock_llm_payload,expected_action",
    [
        (
            "incomplete_answer",
            "Normalization is used to organize data in tables.",
            {
                "evaluation": {
                    "score": 48, "technical_correctness": 14, "conceptual_understanding": 10,
                    "relevance": 12, "completeness": 4, "clarity": 4, "communication": 4,
                },
                "answer_category": "incomplete",
                "strengths": ["Identifies basic purpose of table organization"],
                "weaknesses": ["Omits redundancy elimination and normal forms"],
                "correct_concepts": ["Table organization"],
                "incorrect_concepts": [],
                "missing_concepts": ["Redundancy reduction", "Update anomalies", "1NF/2NF/3NF"],
                "feedback": "Good start, but missing how normalization prevents anomalies.",
                "communication_feedback": "Concise but needs deeper technical detail.",
                "next_action": "FOLLOW_UP",
                "next_question": "Can you explain how normalization reduces data redundancy and what anomalies it prevents?",
                "reason_for_next_question": "Candidate missed redundancy and anomaly prevention.",
                "recommended_difficulty": "medium",
            },
            "FOLLOW_UP",
        ),
        (
            "incorrect_answer",
            "Normalization duplicates columns across tables so queries run faster without joins.",
            {
                "evaluation": {
                    "score": 25, "technical_correctness": 4, "conceptual_understanding": 4,
                    "relevance": 8, "completeness": 3, "clarity": 3, "communication": 3,
                },
                "answer_category": "incorrect",
                "strengths": ["Mentions query performance trade-off"],
                "weaknesses": ["Confuses normalization with denormalization"],
                "correct_concepts": [],
                "incorrect_concepts": ["Claims normalization duplicates columns"],
                "missing_concepts": ["Eliminating redundant data", "Functional dependencies"],
                "feedback": "Confuses normalization with denormalization.",
                "communication_feedback": "Clear delivery, inaccurate technical premise.",
                "next_action": "FOLLOW_UP",
                "next_question": "If duplicating columns speeds up reads, what happens when you need to update a value stored in five places?",
                "reason_for_next_question": "Probe misunderstanding without giving away the answer immediately.",
                "recommended_difficulty": "easy",
            },
            "FOLLOW_UP",
        ),
        (
            "excellent_answer",
            "Normalization decomposes tables using functional dependencies across 1NF, 2NF, 3NF, and BCNF to eliminate redundancy and insertion/update/deletion anomalies, though we occasionally denormalize read-heavy OLAP schemas.",
            {
                "evaluation": {
                    "score": 94, "technical_correctness": 29, "conceptual_understanding": 19,
                    "relevance": 15, "completeness": 14, "clarity": 9, "communication": 8,
                },
                "answer_category": "excellent",
                "strengths": ["Covers 1NF-BCNF", "Explains anomalies and denormalization trade-off"],
                "weaknesses": [],
                "correct_concepts": ["Functional dependencies", "Anomalies", "BCNF", "Denormalization"],
                "incorrect_concepts": [],
                "missing_concepts": [],
                "feedback": "Comprehensive, rigorous explanation with real-world OLAP trade-off.",
                "communication_feedback": "Structured and articulate.",
                "next_action": "NEXT_QUESTION",
                "next_question": "",
                "reason_for_next_question": "Candidate demonstrated mastery; escalate difficulty.",
                "recommended_difficulty": "hard",
            },
            "NEXT_QUESTION",
        ),
        (
            "irrelevant_answer",
            "I really enjoy playing cricket on weekends and my favorite color is blue.",
            {
                "evaluation": {
                    "score": 5, "technical_correctness": 0, "conceptual_understanding": 0,
                    "relevance": 0, "completeness": 0, "clarity": 2, "communication": 3,
                },
                "answer_category": "irrelevant",
                "strengths": [],
                "weaknesses": ["Completely off-topic"],
                "correct_concepts": [],
                "incorrect_concepts": [],
                "missing_concepts": ["Database normalization"],
                "feedback": "Response did not address the database question.",
                "communication_feedback": "Stay focused on the technical prompt.",
                "next_action": "FOLLOW_UP",
                "next_question": "Let's bring the focus back to databases: how do you avoid repeating customer addresses across multiple order rows?",
                "reason_for_next_question": "Redirect off-topic answer back to prompt.",
                "recommended_difficulty": "medium",
            },
            "FOLLOW_UP",
        ),
        (
            "very_short_answer",
            "It removes duplicates.",
            {
                "evaluation": {
                    "score": 32, "technical_correctness": 10, "conceptual_understanding": 6,
                    "relevance": 10, "completeness": 2, "clarity": 2, "communication": 2,
                },
                "answer_category": "too_short",
                "strengths": ["Correct core intuition"],
                "weaknesses": ["Too brief to demonstrate depth"],
                "correct_concepts": ["Duplicate removal"],
                "incorrect_concepts": [],
                "missing_concepts": ["Normal forms", "Foreign keys", "Anomalies"],
                "feedback": "Accurate intuition but far too brief.",
                "communication_feedback": "Elaborate with definitions and examples.",
                "next_action": "FOLLOW_UP",
                "next_question": "Could you elaborate on what kinds of duplicates it removes and give an example of splitting a table?",
                "reason_for_next_question": "Request elaboration on very short answer.",
                "recommended_difficulty": "medium",
            },
            "FOLLOW_UP",
        ),
    ],
)
def test_adaptive_interview_scenarios_and_end_to_end_flow(
    audio_env, scenario_name, transcript, mock_llm_payload, expected_action
):
    """Test all 5 mandatory adaptive scenarios + Question Bank integration + user isolation + report."""
    _, _, tok1, tok2 = audio_env
    from src.api.main import app
    client = TestClient(app)

    # 1. Unauthenticated request blocked
    assert client.post("/api/v1/audio-interview/start", json={"interview_round": "Technical"}).status_code == 401

    # 2. Start interview calibrated to dossier (reads role & company from DB dossier)
    start_res = client.post(
        "/api/v1/audio-interview/start",
        json={
            "interview_round": "Technical",
            "difficulty": "medium",
            "max_questions": 3,
        },
        headers={"x-session-token": tok1},
    )
    assert start_res.status_code == 200
    sdata = start_res.json()
    sid = sdata["session_id"]
    assert sdata["job_role"] == "Software Development Engineer"
    assert sdata["company"] == "Acme Cloud"
    assert sdata["interview_round"] == "Technical"
    assert "question_bank" in sdata["current_question"]["source"]

    # 3. Other user cannot access or submit to user 1's session (403)
    assert client.get(f"/api/v1/audio-interview/{sid}", headers={"x-session-token": tok2}).status_code == 403

    # 4. Upload audio -> Transcribe (mocked Whisper STT so test works offline deterministically)
    wav_bytes = _make_dummy_wav_bytes()
    mock_stt = {
        "transcript": transcript,
        "duration_seconds": 6.5,
        "confidence": 0.94,
        "no_speech_prob": 0.02,
        "noise_warning": None,
        "fluency_metrics": compute_fluency_metrics(transcript, 6.5),
    }
    with patch("src.api.routes.audio_interview.transcribe_audio_groq", return_value=mock_stt):
        tr_res = client.post(
            f"/api/v1/audio-interview/{sid}/transcribe",
            files={"file": ("ans.wav", wav_bytes, "audio/wav")},
            headers={"x-session-token": tok1},
        )
    assert tr_res.status_code == 200
    tr_data = tr_res.json()
    assert tr_data["transcript"] == transcript

    # 5. Submit turn for adaptive LLM evaluation
    with patch(
        "src.interviewer.audio_interviewer._call_groq_chat",
        return_value=(json.dumps(mock_llm_payload), "groq:mock"),
    ):
        turn_res = client.post(
            f"/api/v1/audio-interview/{sid}/submit-turn",
            json={
                "transcript": tr_data["transcript"],
                "audio_duration": tr_data["duration_seconds"],
                "stt_confidence": tr_data["confidence"],
                "fluency_metrics": tr_data["fluency_metrics"],
                "audio_path": tr_data["audio_path"],
            },
            headers={"x-session-token": tok1},
        )
    assert turn_res.status_code == 200
    tdata = turn_res.json()
    assert tdata["next_action"] == expected_action
    if expected_action == "FOLLOW_UP":
        assert tdata["is_followup"] is True
        assert tdata["next_question"]["question_text"] == mock_llm_payload["next_question"]
    elif expected_action == "NEXT_QUESTION":
        assert tdata["is_followup"] is False
        assert tdata["next_question"]["difficulty"] == "hard"

    # 6. End interview & verify comprehensive report + audio replay + history
    end_res = client.post(f"/api/v1/audio-interview/{sid}/end", headers={"x-session-token": tok1})
    assert end_res.status_code == 200
    rep = end_res.json()["report"]
    assert rep["overall_score"] == mock_llm_payload["evaluation"]["score"]
    assert len(rep["turns"]) == 1
    assert "action_plan" in rep

    aud_res = client.get(f"/api/v1/audio-interview/{sid}/audio/0", headers={"x-session-token": tok1})
    assert aud_res.status_code == 200

    hist_res = client.get("/api/v1/audio-interview/history", headers={"x-session-token": tok1})
    assert hist_res.status_code == 200
    assert any(h["session_id"] == sid and h["status"] == "completed" for h in hist_res.json()["sessions"])
