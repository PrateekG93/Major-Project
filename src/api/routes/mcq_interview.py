"""
MCQ Interview Routes
======================
POST /api/v1/mcq/start           — Start an MCQ interview session
POST /api/v1/mcq/answer          — Submit an MCQ answer
GET  /api/v1/mcq/result/{id}     — Get full MCQ session results
GET  /api/v1/mcq/latest          — Get latest completed session for current user
"""

import uuid
import time

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional

from src.auth.session_manager import validate_session
from src.interviewer.mcq_generator import generate_mcq_questions
from src.utils.checkpoint import (
    get_user_documents, save_mcq_session, update_mcq_session,
    save_mcq_answer, get_mcq_session, get_mcq_answers,
    get_latest_mcq_session, get_user_mcq_sessions,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# In-memory session cache
_mcq_sessions: dict = {}


class MCQStartRequest(BaseModel):
    num_questions: int = Field(10, description="Number of MCQ questions", ge=3, le=25)


class MCQStartResponse(BaseModel):
    session_id: str
    total_questions: int
    topics: list[str]
    first_question: dict


class MCQAnswerRequest(BaseModel):
    session_id: str = Field(..., description="Active MCQ session ID")
    selected_option: str = Field(..., description="Selected option: A, B, C, or D")
    response_time: float = Field(0.0, description="Time taken in seconds")
    is_timeout: bool = Field(False, description="Whether this was a timeout auto-submit")


class MCQAnswerResponse(BaseModel):
    is_correct: bool
    correct_answer: str
    explanation: str
    score_so_far: dict
    next_question: Optional[dict] = None
    is_complete: bool
    progress: dict


@router.post("/mcq/start", response_model=MCQStartResponse)
async def start_mcq(
    request: MCQStartRequest,
    x_session_token: Optional[str] = Header(None),
):
    """
    Start a new MCQ interview session.
    Requires user to have uploaded resume and JD.
    """
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    email = validate_session(x_session_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Get user's resume and JD
    docs = get_user_documents(email)
    if not docs["resume"] or not docs["jd"]:
        missing = []
        if not docs["resume"]:
            missing.append("Resume")
        if not docs["jd"]:
            missing.append("Job Description")
        raise HTTPException(
            status_code=400,
            detail=f"Please upload your {' and '.join(missing)} first in the Upload Documents section.",
        )

    resume_text = docs["resume"]["content_text"]
    jd_text = docs["jd"]["content_text"]

    # Generate MCQ questions
    try:
        questions = generate_mcq_questions(
            jd_text=jd_text,
            resume_text=resume_text,
            num_questions=request.num_questions,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate questions: {str(e)}")

    if not questions:
        raise HTTPException(status_code=500, detail="Could not generate any questions.")

    # Create session
    session_id = f"mcq_{uuid.uuid4().hex[:8]}"
    session_state = {
        "questions": questions,
        "current_index": 0,
        "answers": [],
        "total_correct": 0,
        "topics": list({q.get("topic", "General") for q in questions}),
    }

    # Save to database
    save_mcq_session(session_id, email, len(questions), session_state)

    # Cache in memory
    _mcq_sessions[session_id] = {
        "email": email,
        "state": session_state,
    }

    first_q = questions[0]
    return MCQStartResponse(
        session_id=session_id,
        total_questions=len(questions),
        topics=session_state["topics"],
        first_question={
            "index": 0,
            "question_text": first_q["question_text"],
            "options": first_q["options"],
            "topic": first_q.get("topic", "General"),
            "difficulty": first_q.get("difficulty", "medium"),
        },
    )


@router.post("/mcq/answer", response_model=MCQAnswerResponse)
async def submit_mcq_answer(
    request: MCQAnswerRequest,
    x_session_token: Optional[str] = Header(None),
):
    """Submit an MCQ answer and get the result + next question."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    email = validate_session(x_session_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Load session
    cached = _mcq_sessions.get(request.session_id)
    if not cached:
        # Try loading from DB
        db_session = get_mcq_session(request.session_id)
        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")
        cached = {"email": db_session["email"], "state": db_session["state"]}
        _mcq_sessions[request.session_id] = cached

    state = cached["state"]
    current_idx = state["current_index"]
    questions = state["questions"]

    if current_idx >= len(questions):
        raise HTTPException(status_code=400, detail="Interview is already complete")

    current_q = questions[current_idx]
    correct_answer = current_q["correct_answer"]

    # Normalize answer
    selected = request.selected_option.strip().upper()
    if request.is_timeout:
        selected = ""  # No answer on timeout

    is_correct = selected == correct_answer and not request.is_timeout

    if is_correct:
        state["total_correct"] += 1

    # Record answer
    state["answers"].append({
        "question_index": current_idx,
        "selected": selected,
        "correct": correct_answer,
        "is_correct": is_correct,
        "is_timeout": request.is_timeout,
        "response_time": request.response_time,
    })

    # Save individual answer to DB
    save_mcq_answer(
        session_id=request.session_id,
        question_index=current_idx,
        question_text=current_q["question_text"],
        options=current_q["options"],
        correct_answer=correct_answer,
        user_answer=selected,
        is_correct=is_correct,
        is_timeout=request.is_timeout,
        response_time=request.response_time,
        topic=current_q.get("topic", ""),
        explanation=current_q.get("explanation", ""),
    )

    # Advance
    state["current_index"] += 1
    is_complete = state["current_index"] >= len(questions)

    # Update session in DB
    update_mcq_session(
        session_id=request.session_id,
        total_correct=state["total_correct"],
        total_answered=len(state["answers"]),
        is_complete=is_complete,
        state=state,
    )

    # Build next question
    next_question = None
    if not is_complete:
        next_q = questions[state["current_index"]]
        next_question = {
            "index": state["current_index"],
            "question_text": next_q["question_text"],
            "options": next_q["options"],
            "topic": next_q.get("topic", "General"),
            "difficulty": next_q.get("difficulty", "medium"),
        }

    return MCQAnswerResponse(
        is_correct=is_correct,
        correct_answer=correct_answer,
        explanation=current_q.get("explanation", ""),
        score_so_far={
            "correct": state["total_correct"],
            "total": len(state["answers"]),
            "percentage": round(state["total_correct"] / len(state["answers"]) * 100, 1),
        },
        next_question=next_question,
        is_complete=is_complete,
        progress={
            "current": state["current_index"] + 1,
            "total": len(questions),
            "answered": len(state["answers"]),
        },
    )


@router.get("/mcq/result/{session_id}")
async def get_mcq_result(
    session_id: str,
    x_session_token: Optional[str] = Header(None),
):
    """Get full results for an MCQ session."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = get_mcq_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = get_mcq_answers(session_id)

    # Compute topic breakdown
    topic_scores = {}
    for ans in answers:
        topic = ans.get("topic", "General")
        if topic not in topic_scores:
            topic_scores[topic] = {"correct": 0, "total": 0}
        topic_scores[topic]["total"] += 1
        if ans["is_correct"]:
            topic_scores[topic]["correct"] += 1

    topic_breakdown = {
        topic: round(data["correct"] / data["total"] * 100, 1)
        for topic, data in topic_scores.items()
        if data["total"] > 0
    }

    return {
        "session_id": session_id,
        "email": session["email"],
        "num_questions": session["num_questions"],
        "total_correct": session["total_correct"],
        "total_answered": session["total_answered"],
        "is_complete": session["is_complete"],
        "score_percentage": round(session["total_correct"] / max(session["total_answered"], 1) * 100, 1),
        "topic_breakdown": topic_breakdown,
        "answers": answers,
    }


@router.get("/mcq/latest")
async def get_latest_result(x_session_token: Optional[str] = Header(None)):
    """Get the latest completed MCQ session for the current user."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    email = validate_session(x_session_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    session = get_latest_mcq_session(email)
    if not session:
        raise HTTPException(status_code=404, detail="No completed MCQ sessions found.")

    answers = get_mcq_answers(session["session_id"])

    # Topic breakdown
    topic_scores = {}
    for ans in answers:
        topic = ans.get("topic", "General")
        if topic not in topic_scores:
            topic_scores[topic] = {"correct": 0, "total": 0}
        topic_scores[topic]["total"] += 1
        if ans["is_correct"]:
            topic_scores[topic]["correct"] += 1

    topic_breakdown = {
        topic: round(data["correct"] / data["total"] * 100, 1)
        for topic, data in topic_scores.items()
        if data["total"] > 0
    }

    return {
        "session_id": session["session_id"],
        "num_questions": session["num_questions"],
        "total_correct": session["total_correct"],
        "total_answered": session["total_answered"],
        "score_percentage": round(session["total_correct"] / max(session["total_answered"], 1) * 100, 1),
        "topic_breakdown": topic_breakdown,
        "answers": answers,
    }


@router.get("/mcq/sessions")
async def get_user_sessions(x_session_token: Optional[str] = Header(None)):
    """Get all MCQ sessions for the current user."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    email = validate_session(x_session_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    sessions = get_user_mcq_sessions(email)
    return {"sessions": sessions}
