"""
Mock Interview Routes
======================
POST /api/v1/interview/start  — Initialize a new interview session
POST /api/v1/interview/answer — Submit an answer and get the next question
GET  /api/v1/interview/{id}   — Get session status and progress
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from src.interviewer.question_generator import (
    create_interview_session,
    submit_answer,
    resume_session,
)
from src.ml_scoring.model import predict_score
from src.utils.checkpoint import save_score
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# In-memory session store (in production, use Redis or database)
_active_sessions: dict = {}


class InterviewStartRequest(BaseModel):
    target_role: str = Field(..., description="Target job role, e.g., 'Machine Learning Engineer'")
    resume_text: str = Field(..., description="Full text content of the candidate's resume")
    jd_text: Optional[str] = Field(None, description="Optional job description text")
    experience_level: str = Field("Junior", description="Experience level: Junior, Mid, Senior")
    num_questions: int = Field(10, description="Number of questions in the session", ge=3, le=25)


class InterviewStartResponse(BaseModel):
    session_id: str
    target_role: str
    matched_topics: list[str]
    total_questions: int
    first_question: dict


class AnswerSubmitRequest(BaseModel):
    session_id: str = Field(..., description="Active interview session ID")
    answer_text: str = Field(..., description="The candidate's answer to the current question")
    response_time_seconds: float = Field(0.0, description="Time taken to answer in seconds")


class AnswerSubmitResponse(BaseModel):
    score: float
    grade: str
    feedback: dict
    next_question: Optional[dict]
    is_complete: bool
    progress: dict


@router.post("/interview/start", response_model=InterviewStartResponse)
async def start_interview(request: InterviewStartRequest):
    """
    Start a new mock interview session.

    Analyzes the resume against the target role, selects relevant questions,
    and returns the first question to begin the interview.
    """
    if not request.resume_text.strip():
        raise HTTPException(status_code=400, detail="Resume text cannot be empty")

    try:
        session = create_interview_session(
            resume_text=request.resume_text,
            target_role=request.target_role,
            jd_text=request.jd_text,
            experience_level=request.experience_level,
            num_questions=request.num_questions,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create interview session: {str(e)}",
        )

    # Store session in memory
    _active_sessions[session.session_id] = session

    first_q = session.current_question
    if not first_q:
        raise HTTPException(
            status_code=500,
            detail="No questions could be generated for this role/resume combination.",
        )

    return InterviewStartResponse(
        session_id=session.session_id,
        target_role=session.target_role,
        matched_topics=session.topics,
        total_questions=len(session.questions),
        first_question={
            "question_id": first_q.question_id,
            "topic": first_q.topic,
            "difficulty": first_q.difficulty,
            "question_text": first_q.question_text,
        },
    )


@router.post("/interview/answer", response_model=AnswerSubmitResponse)
async def submit_interview_answer(request: AnswerSubmitRequest):
    """
    Submit an answer to the current interview question.

    Scores the answer using the ML model, records the score,
    and returns the next question (or marks the session as complete).
    """
    # Load session
    session = _active_sessions.get(request.session_id)
    if not session:
        # Try to resume from checkpoint
        session = resume_session(request.session_id)
        if session:
            _active_sessions[request.session_id] = session
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    if session.is_complete:
        raise HTTPException(status_code=400, detail="This interview session is already complete")

    current_q = session.current_question
    if not current_q:
        raise HTTPException(status_code=400, detail="No more questions in this session")

    # Score the answer using ML model
    try:
        score_result = predict_score(
            answer_text=request.answer_text,
            reference_answer=current_q.reference_answer,
            response_time=request.response_time_seconds,
        )
    except Exception as e:
        logger.error(f"Scoring failed: {e}")
        score_result = {"score": 0.5, "grade": "Unknown", "features": {}}

    # Record the score in the database
    try:
        save_score(
            session_id=request.session_id,
            question_id=current_q.question_id,
            topic=current_q.topic,
            score=score_result["score"],
            response_time=request.response_time_seconds,
            features=score_result.get("features"),
        )
    except Exception as e:
        logger.warning(f"Could not persist score: {e}")

    # Submit the answer and advance the session
    result = submit_answer(
        session=session,
        answer_text=request.answer_text,
        response_time=request.response_time_seconds,
    )

    return AnswerSubmitResponse(
        score=score_result["score"],
        grade=score_result["grade"],
        feedback={
            "features": {
                k: round(v, 3) if isinstance(v, float) else v
                for k, v in score_result.get("features", {}).items()
            },
        },
        next_question=result.get("next_question"),
        is_complete=result.get("is_complete", False),
        progress=result.get("progress", {}),
    )


@router.get("/interview/{session_id}")
async def get_interview_status(session_id: str):
    """
    Get the current status and progress of an interview session.
    """
    session = _active_sessions.get(session_id)
    if not session:
        session = resume_session(session_id)
        if session:
            _active_sessions[session_id] = session
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    current_q = session.current_question
    return {
        "session_id": session.session_id,
        "target_role": session.target_role,
        "topics": session.topics,
        "is_complete": session.is_complete,
        "progress": session.progress,
        "current_question": {
            "question_id": current_q.question_id,
            "topic": current_q.topic,
            "difficulty": current_q.difficulty,
            "question_text": current_q.question_text,
        }
        if current_q
        else None,
        "answers_submitted": len(session.answers),
    }
