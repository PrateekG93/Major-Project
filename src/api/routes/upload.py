"""
Document Upload Route (Resume + JD)
=====================================
POST /api/v1/upload/resume     — Upload and parse resume
POST /api/v1/upload/jd         — Upload JD (file or text)
GET  /api/v1/upload/documents  — Get current user's resume/JD
"""

import os

from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from src.auth.session_manager import validate_session
from src.document_intelligence.parser import parse_document, SUPPORTED_FORMATS
from src.utils.checkpoint import save_user_document, get_user_documents
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

UPLOAD_DIR = "./data/raw_documents"


def _get_user_email(token: Optional[str]) -> str:
    """Extract user email from session token or raise 401."""
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    email = validate_session(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return email


@router.post("/upload/resume")
async def upload_resume(
    file: UploadFile = File(...),
    x_session_token: Optional[str] = Header(None),
):
    """
    Upload a resume (PDF or DOCX). Parses it and stores the text per user.
    """
    email = _get_user_email(x_session_token)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(
            status_code=400,
            detail="Resume must be PDF, DOCX, or TXT format.",
        )

    # Save file temporarily
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    temp_path = os.path.join(UPLOAD_DIR, f"resume_{email.replace('@', '_')}_{file.filename}")

    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Parse
        document = parse_document(temp_path, doc_type="resume")
        if not document.pages:
            raise HTTPException(status_code=422, detail="Could not extract text from resume.")

        # Combine all pages into full text
        full_text = "\n\n".join(
            page.text for page in document.pages if page.text.strip()
        )

        if not full_text.strip():
            raise HTTPException(status_code=422, detail="Resume appears to be empty.")

        # Store in database
        save_user_document(email, "resume", full_text, file.filename)

        return {
            "status": "success",
            "filename": file.filename,
            "text_length": len(full_text),
            "preview": full_text[:500] + "..." if len(full_text) > 500 else full_text,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {str(e)}")
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/upload/jd")
async def upload_jd(
    file: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
    x_session_token: Optional[str] = Header(None),
):
    """
    Upload a Job Description. Accepts either a file (PDF/DOCX/TXT) or plain text.
    """
    email = _get_user_email(x_session_token)

    final_text = ""
    filename = ""

    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in {".pdf", ".docx", ".txt"}:
            raise HTTPException(status_code=400, detail="JD must be PDF, DOCX, or TXT.")

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        temp_path = os.path.join(UPLOAD_DIR, f"jd_{email.replace('@', '_')}_{file.filename}")

        try:
            with open(temp_path, "wb") as f:
                content = await file.read()
                f.write(content)

            document = parse_document(temp_path, doc_type="notes")
            final_text = "\n\n".join(
                page.text for page in document.pages if page.text.strip()
            )
            filename = file.filename
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    elif jd_text and jd_text.strip():
        final_text = jd_text.strip()
        filename = "pasted_text"
    else:
        raise HTTPException(status_code=400, detail="Provide either a file or text for the JD.")

    if not final_text.strip():
        raise HTTPException(status_code=422, detail="JD appears to be empty.")

    save_user_document(email, "jd", final_text, filename)

    return {
        "status": "success",
        "filename": filename,
        "text_length": len(final_text),
        "preview": final_text[:500] + "..." if len(final_text) > 500 else final_text,
    }


@router.get("/upload/documents")
async def get_documents(x_session_token: Optional[str] = Header(None)):
    """Get current user's uploaded resume and JD."""
    email = _get_user_email(x_session_token)
    docs = get_user_documents(email)

    return {
        "email": email,
        "resume": {
            "uploaded": docs["resume"] is not None,
            "filename": docs["resume"]["filename"] if docs["resume"] else None,
            "text_length": len(docs["resume"]["content_text"]) if docs["resume"] else 0,
            "preview": docs["resume"]["content_text"][:500] if docs["resume"] else None,
        },
        "jd": {
            "uploaded": docs["jd"] is not None,
            "filename": docs["jd"]["filename"] if docs["jd"] else None,
            "text_length": len(docs["jd"]["content_text"]) if docs["jd"] else 0,
            "preview": docs["jd"]["content_text"][:500] if docs["jd"] else None,
        },
    }
