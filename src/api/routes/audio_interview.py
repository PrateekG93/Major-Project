"""
Adaptive AI Audio Interview API Routes
=========================================
POST /api/v1/audio-interview/start                     — Start stateful adaptive audio interview
POST /api/v1/audio-interview/{session_id}/transcribe   — Upload audio -> Whisper STT + fluency metrics
POST /api/v1/audio-interview/{session_id}/submit-turn  — Evaluate transcript -> adaptive next action
POST /api/v1/audio-interview/{session_id}/submit-audio — One-step upload + transcribe + evaluate
GET  /api/v1/audio-interview/history                   — User's audio interview history
GET  /api/v1/audio-interview/{session_id}              — Get/resume session state
POST /api/v1/audio-interview/{session_id}/end          — End session early & generate final report
GET  /api/v1/audio-interview/{session_id}/report       — Fetch final performance report
GET  /api/v1/audio-interview/{session_id}/audio/{turn} — Replay retained audio recording
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.auth.dependencies import get_current_user
from src.interviewer.audio_interviewer import (
    finalize_audio_interview,
    get_audio_session_state,
    get_user_audio_history,
    start_audio_interview,
    submit_audio_turn,
)
from src.interviewer.audio_service import (
    cleanup_expired_audio,
    compute_fluency_metrics,
    save_audio_upload,
    transcribe_audio_groq,
)
from src.utils.checkpoint import get_user_documents
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class AudioInterviewStartRequest(BaseModel):
    interview_round: str = Field("Technical", description="Technical | HR / Behavioral | System Design | Managerial")
    difficulty: str = Field("medium", description="easy | medium | hard")
    max_questions: int = Field(5, ge=1, le=15)
    max_duration_minutes: int = Field(20, ge=5, le=90)
    custom_weights: Optional[dict[str, int]] = None
    initial_question: str = Field("", description="Optional question pre-selected from Question Bank")
    initial_topic: str = Field("", description="Optional topic for initial question")


class SubmitTurnRequest(BaseModel):
    transcript: str = Field(..., description="Reviewed speech-to-text transcript")
    audio_duration: float = Field(0.0, ge=0.0)
    stt_confidence: float = Field(1.0, ge=0.0, le=1.0)
    fluency_metrics: Optional[dict] = None
    audio_path: str = Field("", description="Retained audio path returned by /transcribe")


@router.post("/audio-interview/start")
async def api_start_audio_interview(
    request: AudioInterviewStartRequest,
    email: str = Depends(get_current_user),
):
    """Initialize a new stateful adaptive AI audio interview session using user's uploaded dossier."""
    cleanup_expired_audio()
    docs = get_user_documents(email)
    resume_doc = docs.get("resume")
    jd_doc = docs.get("jd")

    if not resume_doc or not jd_doc:
        raise HTTPException(
            status_code=400,
            detail="Please upload both your Resume and Job Description on 01 — Upload Dossier first.",
        )

    resume_text = resume_doc["content_text"]
    jd_text = jd_doc["content_text"]
    dossier_role = jd_doc.get("parsed_role") or "Software Engineer"
    dossier_company = jd_doc.get("parsed_company") or ""

    try:
        return start_audio_interview(
            email=email,
            job_role=dossier_role,
            company=dossier_company,
            interview_round=request.interview_round,
            difficulty=request.difficulty,
            max_questions=request.max_questions,
            max_duration_minutes=request.max_duration_minutes,
            custom_weights=request.custom_weights,
            resume_text=resume_text,
            jd_text=jd_text,
            initial_question=request.initial_question,
            initial_topic=request.initial_topic,
        )
    except Exception as e:
        logger.error(f"Failed starting audio interview: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start audio interview: {str(e)}")


@router.post("/audio-interview/{session_id}/transcribe")
async def api_transcribe_audio(
    session_id: str,
    file: UploadFile = File(...),
    email: str = Depends(get_current_user),
):
    """
    Upload recorded/selected audio, validate format/size, store securely,
    and transcribe via Groq Whisper for user transcript review/retry.
    """
    try:
        data = get_audio_session_state(session_id, email)
    except ValueError:
        raise HTTPException(status_code=404, detail="Audio interview session not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied to this session.")

    if data["session"]["status"] != "active":
        raise HTTPException(status_code=400, detail="Interview session is no longer active.")

    turn_idx = data["session"]["current_question_index"]
    contents = await file.read()

    try:
        audio_path = save_audio_upload(session_id, turn_idx, file.filename or "recording.wav", contents)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    try:
        stt_res = transcribe_audio_groq(audio_path)
    except Exception as e:
        logger.error(f"STT failed for {session_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Transcription failed: {str(e)}")

    stt_res["audio_path"] = audio_path
    stt_res["turn_index"] = turn_idx
    return stt_res


@router.post("/audio-interview/{session_id}/submit-turn")
async def api_submit_audio_turn(
    session_id: str,
    request: SubmitTurnRequest,
    email: str = Depends(get_current_user),
):
    """Evaluate confirmed transcript and adaptively choose FOLLOW_UP / NEXT_QUESTION / END_INTERVIEW."""
    fluency = request.fluency_metrics or compute_fluency_metrics(request.transcript, request.audio_duration)
    try:
        return submit_audio_turn(
            session_id=session_id,
            email=email,
            transcript=request.transcript,
            audio_duration=request.audio_duration,
            stt_confidence=request.stt_confidence,
            fluency_metrics=fluency,
            audio_path=request.audio_path,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied to this session.")
    except Exception as e:
        logger.error(f"Submit turn failed for {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.post("/audio-interview/{session_id}/submit-audio")
async def api_submit_audio_direct(
    session_id: str,
    file: UploadFile = File(...),
    email: str = Depends(get_current_user),
):
    """One-step endpoint: upload audio -> Whisper STT -> adaptive LLM evaluation."""
    stt_res = await api_transcribe_audio(session_id=session_id, file=file, email=email)
    if not stt_res.get("transcript"):
        raise HTTPException(
            status_code=422,
            detail=stt_res.get("noise_warning") or "Empty speech transcript. Please re-record clearly.",
        )

    turn_res = submit_audio_turn(
        session_id=session_id,
        email=email,
        transcript=stt_res["transcript"],
        audio_duration=stt_res["duration_seconds"],
        stt_confidence=stt_res["confidence"],
        fluency_metrics=stt_res["fluency_metrics"],
        audio_path=stt_res["audio_path"],
    )
    turn_res["transcription"] = stt_res
    return turn_res


@router.get("/audio-interview/history")
async def api_audio_history(email: str = Depends(get_current_user)):
    """Get all audio interview sessions for the authenticated user."""
    return {"sessions": get_user_audio_history(email)}


@router.get("/audio-interview/{session_id}")
async def api_get_audio_session(
    session_id: str,
    email: str = Depends(get_current_user),
):
    """Get full stateful session details and turn history for resumption."""
    try:
        return get_audio_session_state(session_id, email)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied.")


@router.post("/audio-interview/{session_id}/end")
async def api_end_audio_session(
    session_id: str,
    email: str = Depends(get_current_user),
):
    """Complete/cancel the interview session and generate performance report."""
    try:
        report = finalize_audio_interview(session_id, email)
        return {"status": "completed", "report": report}
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied.")


@router.get("/audio-interview/{session_id}/report")
async def api_get_audio_report(
    session_id: str,
    email: str = Depends(get_current_user),
):
    """Fetch final performance report for a completed audio interview."""
    try:
        data = get_audio_session_state(session_id, email)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied.")

    if data["session"]["status"] != "completed" or not data["session"].get("report"):
        report = finalize_audio_interview(session_id, email)
        return report
    return data["session"]["report"]


@router.get("/audio-interview/{session_id}/audio/{turn_index}")
async def api_get_turn_audio(
    session_id: str,
    turn_index: int,
    email: str = Depends(get_current_user),
):
    """Securely stream a retained audio recording for the authenticated owner."""
    try:
        data = get_audio_session_state(session_id, email)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied.")

    matching = [t for t in data["turns"] if t["turn_index"] == turn_index]
    if not matching or not matching[0].get("audio_path"):
        raise HTTPException(status_code=404, detail="Audio recording not found.")

    path = matching[0]["audio_path"]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Audio recording expired per retention policy.")

    return FileResponse(path)
