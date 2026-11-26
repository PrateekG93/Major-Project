"""
Question Bank Seeder & Topic Synchronization Pipeline
=====================================================
Seeds canonical interview questions from data/question_bank/questions.json
(produced by scripts/build_question_bank.py) into SQLite.
"""

import json
import os
import time

from src.interviewer.ingestion import seed_curated_questions
from src.interviewer.sources.open_datasets import OpenDatasetsSource
from src.utils.checkpoint import _get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)

QUESTION_BANK_PATH = os.getenv(
    "QUESTION_BANK_PATH", "./data/question_bank/questions.json"
)


def seed_question_bank(input_path: str = QUESTION_BANK_PATH, replace: bool = False) -> int:
    """
    Seed the SQLite canonical question bank from the JSON file in /data.
    """
    if not os.path.exists(input_path):
        logger.warning(f"Question bank file not found at {input_path}")
        return 0

    with open(input_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    if not isinstance(dataset, list) or not dataset:
        logger.warning(f"Question bank at {input_path} is empty.")
        return 0

    stats = seed_curated_questions(dataset, replace_existing=replace)
    _update_source_sync_status(
        source_name="local_question_bank",
        status="completed",
        fetched=len(dataset),
        added=stats.get("new_canonical", 0),
        dupes=(
            stats.get("duplicate_exact", 0)
            + stats.get("duplicate_lexical", 0)
            + stats.get("duplicate_semantic", 0)
        ),
    )
    logger.info(f"Seeded canonical database from {input_path}: {stats}")
    return len(dataset)


def _update_source_sync_status(
    source_name: str,
    status: str,
    fetched: int = 0,
    added: int = 0,
    dupes: int = 0,
    error: str = "",
) -> None:
    """Persist sync status in source_sync_status table."""
    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO source_sync_status
                (source_name, last_sync_at, last_status, questions_fetched, questions_added, duplicates_found, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_name) DO UPDATE SET
                last_sync_at = excluded.last_sync_at,
                last_status = excluded.last_status,
                questions_fetched = excluded.questions_fetched,
                questions_added = excluded.questions_added,
                duplicates_found = excluded.duplicates_found,
                error_message = excluded.error_message
            """,
            (source_name, time.time(), status, fetched, added, dupes, error[:500]),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"Failed updating sync status for {source_name}: {e}")
    finally:
        conn.close()


def get_source_sync_statuses() -> list[dict]:
    """Retrieve synchronization status records."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            """
            SELECT source_name, last_sync_at, last_status, questions_fetched,
                   questions_added, duplicates_found, error_message
            FROM source_sync_status
            ORDER BY last_sync_at DESC
            """
        )
        return [
            {
                "source_name": r[0],
                "last_sync_at": r[1],
                "last_status": r[2],
                "questions_fetched": r[3],
                "questions_added": r[4],
                "duplicates_found": r[5],
                "error_message": r[6],
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def get_bank_stats() -> dict:
    """Return statistics about the question bank from SQLite (by topic, round, difficulty)."""
    conn = _get_connection()
    try:
        total_canonical = conn.execute("SELECT COUNT(*) FROM canonical_questions").fetchone()[0]
        total_sources = conn.execute("SELECT COUNT(*) FROM question_sources").fetchone()[0]

        by_round = dict(
            conn.execute(
                "SELECT interview_round, COUNT(DISTINCT canonical_id) FROM question_sources GROUP BY interview_round"
            ).fetchall()
        )
        by_topic = dict(
            conn.execute(
                "SELECT topic, COUNT(*) FROM canonical_questions GROUP BY topic ORDER BY COUNT(*) DESC"
            ).fetchall()
        )
        by_difficulty = dict(
            conn.execute(
                "SELECT difficulty, COUNT(*) FROM canonical_questions GROUP BY difficulty"
            ).fetchall()
        )

        return {
            "total_canonical": total_canonical,
            "total_sources": total_sources,
            "by_round": by_round,
            "by_topic": by_topic,
            "by_difficulty": by_difficulty,
        }
    finally:
        conn.close()


def sync_all_sources(topic: str = "", replace: bool = False) -> list[dict]:
    """Synchronize local open dataset / generated question bank cleanly."""
    from src.interviewer.ingestion import ingest_questions
    try:
        res = OpenDatasetsSource().collect_questions(topic=topic)
        stats = ingest_questions(res.questions, enable_semantic_dedup=False) if res.questions else {"new_canonical": 0}
        return [{"source": "open_dataset", "status": "completed", "questions_found": len(res.questions), **stats}]
    except Exception as exc:
        logger.error(f"Question bank sync failed: {exc}")
        _update_source_sync_status("open_dataset", "failed", error=str(exc))
        return [{"source": "open_dataset", "status": "failed", "error": str(exc)}]
