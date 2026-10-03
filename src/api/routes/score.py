"""
Scoring & Recommendation Routes
=================================
POST /api/v1/score            — Score a single answer with the ML model
GET  /api/v1/score/{session}  — Get full session analytics and recommendations
GET  /api/v1/score/ats        — Compute ATS score from user's resume + JD
"""

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional

from src.auth.session_manager import validate_session
from src.ml_scoring.model import predict_score
from src.ml_scoring.recommendation_engine import get_full_recommendation
from src.ml_scoring.ats_scorer import compute_ats_score, generate_resume_suggestions
from src.rag_assistant.hybrid_retriever import HybridRetriever
from src.utils.checkpoint import get_session_scores, get_topic_averages, get_user_documents
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class ScoreRequest(BaseModel):
    answer_text: str = Field(..., description="The candidate's answer text")
    reference_answer: str = Field("", description="Reference/ideal answer for comparison")
    response_time_seconds: float = Field(0.0, description="Time taken to answer")
    topic: str = Field("General", description="Topic category")
    expected_keywords: Optional[list[str]] = Field(None, description="Keywords to check for")


class ScoreResponse(BaseModel):
    score: float
    grade: str
    features: dict


class SessionAnalyticsResponse(BaseModel):
    session_id: str
    topic_breakdown: dict
    overall_score: float
    readiness: str
    readiness_detail: str
    weak_topics: list[dict]
    study_plan: list[dict]
    total_study_hours: float
    retest_topics: list[dict]


@router.post("/score", response_model=ScoreResponse)
async def score_answer(request: ScoreRequest):
    """
    Score a single answer using the ML model.

    Returns a quality score (0-1), grade, and detailed feature breakdown.
    """
    if not request.answer_text.strip():
        raise HTTPException(status_code=400, detail="Answer text cannot be empty")

    try:
        result = predict_score(
            answer_text=request.answer_text,
            reference_answer=request.reference_answer,
            response_time=request.response_time_seconds,
            expected_keywords=request.expected_keywords,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Scoring failed: {str(e)}",
        )

    return ScoreResponse(
        score=result["score"],
        grade=result["grade"],
        features={
            k: round(v, 3) if isinstance(v, float) else v
            for k, v in result["features"].items()
        },
    )


@router.get("/score/{session_id}", response_model=SessionAnalyticsResponse)
async def get_session_analytics(session_id: str):
    """
    Get comprehensive analytics and study recommendations for a completed session.

    Includes per-topic breakdown, weak area identification, study plan with
    referenced materials, and retest specifications.
    """
    # Retrieve all scores for this session
    scores = get_session_scores(session_id)

    if not scores:
        raise HTTPException(
            status_code=404,
            detail=f"No scores found for session '{session_id}'. Complete some questions first.",
        )

    # Try to get retriever for study material recommendations
    retriever = None
    try:
        retriever = HybridRetriever(collection_name="admin_course_materials")
        if retriever.get_document_count() == 0:
            retriever = None
    except Exception:
        pass

    # Generate full recommendation package
    try:
        recommendation = get_full_recommendation(
            session_scores=scores,
            retriever=retriever,
        )
    except Exception as e:
        logger.error(f"Recommendation generation failed: {e}")
        # Return basic analytics even if full recommendation fails
        topic_avgs = get_topic_averages(session_id)
        return SessionAnalyticsResponse(
            session_id=session_id,
            topic_breakdown=topic_avgs,
            overall_score=sum(topic_avgs.values()) / len(topic_avgs) if topic_avgs else 0,
            readiness="Unknown",
            readiness_detail="Could not generate full analysis. Basic scores shown above.",
            weak_topics=[],
            study_plan=[],
            total_study_hours=0,
            retest_topics=[],
        )

    return SessionAnalyticsResponse(
        session_id=session_id,
        topic_breakdown=recommendation["topic_breakdown"],
        overall_score=recommendation["overall_score"],
        readiness=recommendation["readiness"],
        readiness_detail=recommendation["readiness_detail"],
        weak_topics=recommendation["weak_topics"],
        study_plan=recommendation["study_plan"],
        total_study_hours=recommendation["total_estimated_study_hours"],
        retest_topics=recommendation["retest_specs"],
    )


@router.get("/score/ats/analyze")
async def get_ats_score(x_session_token: Optional[str] = Header(None)):
    """Compute ATS score and resume suggestions from user's resume + JD."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    email = validate_session(x_session_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    docs = get_user_documents(email)
    if not docs["resume"] or not docs["jd"]:
        missing = []
        if not docs["resume"]:
            missing.append("Resume")
        if not docs["jd"]:
            missing.append("Job Description")
        raise HTTPException(
            status_code=400,
            detail=f"Please upload your {' and '.join(missing)} first.",
        )

    resume_text = docs["resume"]["content_text"]
    jd_text = docs["jd"]["content_text"]

    # Compute ATS score
    ats_result = compute_ats_score(resume_text, jd_text)

    # Generate suggestions
    suggestions = generate_resume_suggestions(ats_result, jd_text)

    return {
        "ats_score": ats_result["ats_score"],
        "keyword_score": ats_result.get("keyword_score", 0),
        "section_score": ats_result.get("section_score", 0),
        "verb_score": ats_result.get("verb_score", 0),
        "quant_score": ats_result.get("quant_score", 0),
        "matched_keywords": ats_result["matched_keywords"],
        "missing_keywords": ats_result["missing_keywords"],
        "technical_match": ats_result.get("technical_match", {}),
        "soft_skills_match": ats_result.get("soft_skills_match", {}),
        "sections_found": ats_result.get("sections_found", []),
        "sections_missing": ats_result.get("sections_missing", []),
        "suggestions": suggestions,
    }
