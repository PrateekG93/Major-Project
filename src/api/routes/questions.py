"""
Centralized Interview Question Bank API Routes
================================================
GET    /api/v1/questions/search             — Search, filter, sort, paginate questions
GET    /api/v1/questions/topics             — Browse fixed topics & counts
GET    /api/v1/questions/filters            — Available filter facets
GET    /api/v1/questions/bookmarks          — User's saved/bookmarked questions
POST   /api/v1/questions/{id}/bookmark      — Bookmark a question
DELETE /api/v1/questions/{id}/bookmark      — Remove bookmark
GET    /api/v1/questions/duplicates         — View detected duplicate relationships
POST   /api/v1/questions/import             — Import permitted JSON/CSV question dataset
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.auth.dependencies import get_current_user, get_optional_user
from src.interviewer.ingestion import ingest_questions
from src.interviewer.question_bank_service import (
    bookmark_question,
    get_duplicate_relationships,
    get_filter_facets,
    get_topics_catalog,
    remove_bookmark,
    search_questions,
)
from src.interviewer.sources.open_datasets import OpenDatasetsSource
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class BookmarkRequest(BaseModel):
    notes: str = Field("", description="Optional personal study notes")


class ImportDatasetRequest(BaseModel):
    format: str = Field("json", description="'json' or 'csv'")
    content: str = Field(..., description="Raw JSON array or CSV content")


@router.get("/questions/search")
async def api_search_questions(
    q: str = Query("", description="Keyword search query"),
    interview_round: str = Query("", description="Filter by round (Coding, Technical, HR)"),
    difficulty: str = Query("", description="Filter by difficulty (easy, medium, hard)"),
    topic: str = Query("", description="Filter by topic"),
    is_technical: Optional[bool] = Query(None, description="Filter technical (true) vs non-technical (false)"),
    sort_by: str = Query("relevance", description="Sort: relevance | recent | frequency"),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    bookmarked_only: bool = Query(False),
    scope: str = Query("jd", description="Domain scope: 'jd' (JD-related domains first) | 'all' (all domains)"),
    user_email: Optional[str] = Depends(get_optional_user),
):
    """Search, filter, sort, and paginate the centralized question bank."""
    if bookmarked_only and not user_email:
        raise HTTPException(status_code=401, detail="Authentication required to view bookmarks.")

    return search_questions(
        q=q,
        interview_round=interview_round,
        difficulty=difficulty,
        topic=topic,
        is_technical=is_technical,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
        user_email=user_email,
        bookmarked_only=bookmarked_only,
        scope=scope,
    )


@router.get("/questions/topics")
async def api_list_topics(user_email: Optional[str] = Depends(get_optional_user)):
    """List fixed topics with easy/medium/hard counts and rounds, ordering JD-matched domains first."""
    return {"topics": get_topics_catalog(user_email=user_email)}


@router.get("/questions/filters")
async def api_filter_facets(user_email: Optional[str] = Depends(get_optional_user)):
    """Return distinct facet values for search UI filters and user JD domain context."""
    return get_filter_facets(user_email=user_email)


@router.get("/questions/bookmarks")
async def api_get_bookmarks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    email: str = Depends(get_current_user),
):
    """Get authenticated user's bookmarked questions."""
    return search_questions(
        page=page,
        page_size=page_size,
        user_email=email,
        bookmarked_only=True,
    )


@router.post("/questions/{canonical_id}/bookmark")
async def api_bookmark_question(
    canonical_id: int,
    request: Optional[BookmarkRequest] = None,
    email: str = Depends(get_current_user),
):
    """Bookmark a question for the authenticated user."""
    notes = request.notes if request else ""
    ok = bookmark_question(email, canonical_id, notes=notes)
    if not ok:
        raise HTTPException(status_code=404, detail="Question not found.")
    return {"status": "bookmarked", "canonical_id": canonical_id}


@router.delete("/questions/{canonical_id}/bookmark")
async def api_remove_bookmark(
    canonical_id: int,
    email: str = Depends(get_current_user),
):
    """Remove a question bookmark for the authenticated user."""
    removed = remove_bookmark(email, canonical_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Bookmark not found.")
    return {"status": "removed", "canonical_id": canonical_id}


@router.get("/questions/duplicates")
async def api_list_duplicates(
    canonical_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Inspect detected duplicate relationships and similarity scores."""
    return {"duplicates": get_duplicate_relationships(canonical_id=canonical_id, limit=limit)}


@router.post("/questions/import")
async def api_import_dataset(
    request: ImportDatasetRequest,
    email: str = Depends(get_current_user),
):
    """Import a user-provided JSON or CSV dataset through the deduplication pipeline."""
    try:
        raw_questions = OpenDatasetsSource.parse_user_dataset(request.content, request.format)
        if not raw_questions:
            raise HTTPException(status_code=400, detail="No valid questions found in dataset.")
        stats = ingest_questions(raw_questions)
        return {"status": "imported", "stats": stats}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Dataset import failed: {e}")
        raise HTTPException(status_code=422, detail=f"Failed to import dataset: {str(e)}")
