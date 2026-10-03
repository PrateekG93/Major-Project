"""
Admin Routes
==============
POST /api/v1/admin/login           — Admin email+password verification
POST /api/v1/admin/upload-material — Upload course materials to admin collection
GET  /api/v1/admin/materials       — List all uploaded materials
DELETE /api/v1/admin/materials/{id} — Delete a material
GET  /api/v1/admin/users           — List all registered users
GET  /api/v1/admin/results         — List all MCQ interview results
"""

import os
import uuid

from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from dotenv import load_dotenv

from src.document_intelligence.parser import parse_document, SUPPORTED_FORMATS
from src.document_intelligence.chunker import chunk_document
from src.rag_assistant.hybrid_retriever import HybridRetriever
from src.utils.checkpoint import (
    save_admin_material, get_admin_materials, delete_admin_material,
    get_all_users, get_all_mcq_results,
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
