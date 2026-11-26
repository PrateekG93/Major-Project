"""
ATS Resume Audit Route
======================
GET /api/v1/score/ats/analyze — Compute ATS score and suggestions from user's resume + JD
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from src.auth.session_manager import validate_session
from src.ml_scoring.ats_scorer import compute_ats_score, generate_resume_suggestions
from src.utils.checkpoint import get_user_documents
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


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

    ats_result = compute_ats_score(resume_text, jd_text)
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
