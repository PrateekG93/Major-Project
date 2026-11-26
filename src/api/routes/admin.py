"""
Admin Routes
==============
POST /api/v1/admin/login           — Admin email+password verification
POST /api/v1/admin/upload-material — Upload course materials to admin collection
GET  /api/v1/admin/materials       — List all uploaded materials
DELETE /api/v1/admin/materials/{id} — Delete a material
GET  /api/v1/admin/users           — List all registered users & verification/dossier state
GET  /api/v1/admin/results         — List all MCQ examination results
GET  /api/v1/admin/audio-results   — List all Adaptive AI Audio Interview sessions
GET  /api/v1/admin/otp-status      — Inspect non-secret Email OTP & SMTP status
POST /api/v1/admin/test-smtp       — Verify live SMTP connectivity & credentials
"""

import os
import smtplib
import uuid

from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from dotenv import load_dotenv

from src.auth.otp_manager import _get_smtp_config
from src.document_intelligence.parser import parse_document, SUPPORTED_FORMATS
from src.document_intelligence.chunker import chunk_document
from src.rag_assistant.hybrid_retriever import HybridRetriever
from src.utils.checkpoint import (
    save_admin_material, get_admin_materials, delete_admin_material,
    get_all_users, get_all_mcq_results, get_all_audio_results,
)
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)
router = APIRouter()

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@copilot.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
UPLOAD_DIR = "./data/raw_documents"
ADMIN_COLLECTION = "admin_course_materials"


def _verify_admin(admin_token: Optional[str]) -> bool:
    """Verify admin token (simple base64 of email:password)."""
    if not admin_token:
        return False
    # Simple check: token is "admin_verified"
    return admin_token == "admin_verified"


class AdminLoginRequest(BaseModel):
    email: str
    password: str


@router.post("/admin/login")
async def admin_login(request: AdminLoginRequest):
    """Admin login with email + password."""
    if request.email.strip().lower() != ADMIN_EMAIL.lower():
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    if request.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    return {"success": True, "admin_token": "admin_verified", "message": "Admin login successful."}


@router.post("/admin/upload-material")
async def upload_material(
    file: UploadFile = File(...),
    doc_type: str = Form("textbook"),
    x_admin_token: Optional[str] = Header(None),
):
    """Upload course material (textbooks, lecture notes) for all users' Q&A."""
    if not _verify_admin(x_admin_token):
        raise HTTPException(status_code=403, detail="Admin access required")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Supported: {SUPPORTED_FORMATS}",
        )

    # Save file
    doc_id = f"adm_{uuid.uuid4().hex[:6]}"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}_{file.filename}")

    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Parse
    try:
        document = parse_document(file_path, doc_type=doc_type)
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=422, detail=f"Failed to parse: {str(e)}")

    if not document.pages:
        os.remove(file_path)
        raise HTTPException(status_code=422, detail="Document is empty.")

    # Chunk
    chunks = chunk_document(document, doc_type=doc_type)
    if not chunks:
        raise HTTPException(status_code=422, detail="No text chunks extracted.")

    # Index into admin collection
    try:
        retriever = HybridRetriever(collection_name=ADMIN_COLLECTION)
        num_indexed = retriever.add_documents(chunks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")

    # Track in database
    save_admin_material(doc_id, file.filename, doc_type, num_indexed)

    return {
        "status": "success",
        "doc_id": doc_id,
        "filename": file.filename,
        "chunks_indexed": num_indexed,
        "collection": ADMIN_COLLECTION,
    }


@router.post("/admin/upload-materials-batch")
async def upload_materials_batch(
    files: list[UploadFile] = File(...),
    doc_type: str = Form("textbook"),
    x_admin_token: Optional[str] = Header(None),
):
    """Upload multiple course materials (textbooks, lecture notes) at once."""
    if not _verify_admin(x_admin_token):
        raise HTTPException(status_code=403, detail="Admin access required")

    results = []
    errors = []
    retriever = HybridRetriever(collection_name=ADMIN_COLLECTION)

    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in SUPPORTED_FORMATS:
            errors.append({"filename": file.filename, "error": f"Unsupported format '{ext}'. Supported: {SUPPORTED_FORMATS}"})
            continue

        doc_id = f"adm_{uuid.uuid4().hex[:6]}"
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        file_path = os.path.join(UPLOAD_DIR, f"{doc_id}_{file.filename}")

        try:
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
        except Exception as e:
            errors.append({"filename": file.filename, "error": f"Failed to save: {str(e)}"})
            continue

        try:
            document = parse_document(file_path, doc_type=doc_type)
        except Exception as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            errors.append({"filename": file.filename, "error": f"Failed to parse: {str(e)}"})
            continue

        if not document.pages:
            if os.path.exists(file_path):
                os.remove(file_path)
            errors.append({"filename": file.filename, "error": "Document is empty."})
            continue

        chunks = chunk_document(document, doc_type=doc_type)
        if not chunks:
            errors.append({"filename": file.filename, "error": "No text chunks extracted."})
            continue

        try:
            num_indexed = retriever.add_documents(chunks)
            save_admin_material(doc_id, file.filename, doc_type, num_indexed)
            results.append({
                "doc_id": doc_id,
                "filename": file.filename,
                "chunks_indexed": num_indexed,
            })
        except Exception as e:
            errors.append({"filename": file.filename, "error": f"Indexing failed: {str(e)}"})

    return {
        "status": "success",
        "total_files": len(files),
        "successful": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
        "total_chunks_indexed": sum(r["chunks_indexed"] for r in results),
    }


@router.get("/admin/materials")
async def list_materials(x_admin_token: Optional[str] = Header(None)):
    """List all admin-uploaded course materials."""
    if not _verify_admin(x_admin_token):
        raise HTTPException(status_code=403, detail="Admin access required")

    return {"materials": get_admin_materials()}


@router.delete("/admin/materials/{doc_id}")
async def remove_material(doc_id: str, x_admin_token: Optional[str] = Header(None)):
    """Delete an admin material record."""
    if not _verify_admin(x_admin_token):
        raise HTTPException(status_code=403, detail="Admin access required")

    success = delete_admin_material(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Material not found")

    return {"status": "deleted", "doc_id": doc_id}


@router.get("/admin/users")
async def list_users(x_admin_token: Optional[str] = Header(None)):
    """List all registered users."""
    if not _verify_admin(x_admin_token):
        raise HTTPException(status_code=403, detail="Admin access required")

    return {"users": get_all_users()}


@router.get("/admin/results")
async def list_results(x_admin_token: Optional[str] = Header(None)):
    """List all MCQ interview results across all users."""
    if not _verify_admin(x_admin_token):
        raise HTTPException(status_code=403, detail="Admin access required")

    return {"results": get_all_mcq_results()}


@router.get("/admin/audio-results")
async def list_audio_results(x_admin_token: Optional[str] = Header(None)):
    """List all adaptive AI audio interview sessions across all users."""
    if not _verify_admin(x_admin_token):
        raise HTTPException(status_code=403, detail="Admin access required")

    return {"results": get_all_audio_results()}


@router.get("/admin/otp-status")
async def otp_status(x_admin_token: Optional[str] = Header(None)):
    """Inspect active Email OTP delivery mode and sanitized SMTP settings."""
    if not _verify_admin(x_admin_token):
        raise HTTPException(status_code=403, detail="Admin access required")

    from dotenv import dotenv_values
    env_file = dotenv_values(".env") if os.path.exists(".env") else {}
    req_login_otp = (
        os.environ.get("LOGIN_REQUIRE_OTP")
        or str(env_file.get("LOGIN_REQUIRE_OTP") or "true")
    ).strip().lower() in ("1", "true", "yes")

    cfg = _get_smtp_config()
    user = cfg["username"]
    masked_user = f"{user[:2]}***@{user.split('@', 1)[1]}" if "@" in user and len(user) > 3 else ("(configured)" if user else "")
    return {
        "otp_mode": cfg["mode"],
        "login_require_otp": req_login_otp,
        "smtp_host": cfg["host"],
        "smtp_port": cfg["port"],
        "smtp_username_masked": masked_user,
        "smtp_from_email": cfg["from_email"],
        "smtp_from_name": cfg["from_name"],
        "credentials_configured": bool(cfg["username"] and cfg["password"] and cfg["from_email"]),
    }


@router.post("/admin/test-smtp")
async def test_smtp_connection(x_admin_token: Optional[str] = Header(None)):
    """Verify SMTP server login connectivity without sending an external email."""
    if not _verify_admin(x_admin_token):
        raise HTTPException(status_code=403, detail="Admin access required")

    cfg = _get_smtp_config()
    if not cfg["username"] or not cfg["password"]:
        raise HTTPException(
            status_code=400,
            detail="SMTP_USERNAME or SMTP_PASSWORD missing in .env.",
        )

    try:
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=10) as server:
                server.login(cfg["username"], cfg["password"])
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg["username"], cfg["password"])
        return {
            "success": True,
            "message": f"Authenticated cleanly with {cfg['host']}:{cfg['port']}.",
        }
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(
            status_code=401,
            detail="SMTP authentication failed. For Gmail, enable 2-Step Verification and use a 16-char App Password.",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SMTP connection failed: {exc}")
