"""
Question Bank Management & Seeding API Routes
=============================================
GET  /api/v1/scraping/stats       — Get question bank statistics by topic, round, difficulty
POST /api/v1/scraping/seed        — Seed / refresh question bank from /data JSON
POST /api/v1/scraping/sync-all    — Re-sync local dataset into SQLite
GET  /api/v1/scraping/sync-status — Retrieve synchronization status records
"""

from fastapi import APIRouter, HTTPException, Query

from src.interviewer.scraper_pipeline import (
    get_bank_stats,
    get_source_sync_statuses,
    seed_question_bank,
    sync_all_sources,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/scraping/stats")
async def bank_statistics():
    """Get comprehensive statistics on the question bank by topic, round, and difficulty."""
    try:
        return get_bank_stats()
    except Exception as e:
        logger.error(f"Failed to fetch bank statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scraping/seed")
async def seed_bank(replace: bool = Query(False, description="Replace existing bank records")):
    """Seed or refresh the question bank in SQLite from data/question_bank/questions.json."""
    try:
        count = seed_question_bank(replace=replace)
        return {
            "status": "success",
            "message": f"Question bank seeded cleanly with {count} questions.",
        }
    except Exception as e:
        logger.error(f"Failed to seed question bank: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scraping/sync-all")
async def sync_all(topic: str = Query("", description="Optional topic focus")):
    """Synchronize local dataset records cleanly into SQLite."""
    try:
        results = sync_all_sources(topic=topic)
        return {"status": "completed", "results": results}
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scraping/sync-status")
async def sync_status():
    """Retrieve synchronization status and history."""
    try:
        return {"sources": get_source_sync_statuses()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
