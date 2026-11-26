"""
Question Ingestion Pipeline & Multi-Level Deduplication
=========================================================
Handles the pipeline from raw questions to deduplicated, canonical records in SQLite:

  1. Validation & Plain-Text / Markdown Sanitization
  2. Text Normalization (case, filler prefixes, punctuation, whitespace)
  3. Exact SHA-256 Fingerprint Deduplication
  4. Lexical Near-Duplicate Detection (SequenceMatcher >= 0.88)
  5. Semantic Similarity Duplicate Detection (all-MiniLM-L6-v2 cosine >= 0.90)
  6. Duplicate Relationship Logging (question_duplicates) & Source Provenance
"""

import hashlib
import json
import re
import time
from difflib import SequenceMatcher
from typing import Optional

import numpy as np

from src.interviewer.sources.base_source import RawQuestion
from src.interviewer.sources.classifier import classify_question, classify_round, normalize_topic
from src.utils.checkpoint import _get_connection
from src.utils.logger import get_logger
from src.utils.text_utils import strip_html_markup

logger = get_logger(__name__)

# Thresholds tuned to merge true rephrasings without collapsing distinct variations
NEAR_DUPLICATE_THRESHOLD = 0.88
SEMANTIC_DUPLICATE_THRESHOLD = 0.90


def normalize_text(text: str) -> str:
    """Normalize question text for consistent deduplication."""
    text = strip_html_markup(text).lower().strip()
    text = re.sub(r"^(?:q\d*[\.\):\s]+|question\s*\d*[\.\):\s]+)", "", text)
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(".?!:;")
    return text.strip()


def normalize_for_fingerprint(text: str) -> str:
    """Punctuation- and whitespace-invariant normalization."""
    base = normalize_text(text)
    base = re.sub(r"[^\w\s]", " ", base)
    base = re.sub(r"\s+", " ", base)
    return base.strip()


def compute_fingerprint(normalized_text: str) -> str:
    """Compute SHA-256 fingerprint of normalized text for exact dedup."""
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def is_near_duplicate(text_a: str, text_b: str, threshold: float = 0.85) -> bool:
    """Check if two normalized texts are lexical near-duplicates using SequenceMatcher."""
    return SequenceMatcher(None, text_a, text_b).ratio() >= threshold


def validate_question(raw: RawQuestion) -> bool:
    """Validate a raw question before ingestion."""
    text = strip_html_markup(raw.question_text)
    if not text or len(text) < 10:
        return False
    if len(text.split()) < 2:
        return False
    if sum(1 for c in text if c.isalpha()) < 5:
        return False
    return True


def _find_semantic_or_lexical_duplicate(
    strict_norm: str,
    existing_rows: list[tuple[int, str, str]],
    existing_embeddings: Optional[np.ndarray],
    query_embedding: Optional[np.ndarray],
) -> Optional[tuple[int, float, str]]:
    """Check existing canonical questions for lexical near-duplicate or semantic duplicate."""
    best_lex_id = None
    best_lex_score = 0.0
    for cid, q_text, norm_stored in existing_rows:
        cand_norm = norm_stored or normalize_for_fingerprint(q_text)
        if abs(len(cand_norm) - len(strict_norm)) > max(len(strict_norm), len(cand_norm)) * 0.35:
            continue
        ratio = SequenceMatcher(None, strict_norm, cand_norm).ratio()
        if ratio >= NEAR_DUPLICATE_THRESHOLD and ratio > best_lex_score:
            best_lex_score = ratio
            best_lex_id = cid

    if best_lex_id is not None:
        return best_lex_id, round(best_lex_score, 4), "lexical_near_duplicate"

    if existing_embeddings is not None and query_embedding is not None and len(existing_embeddings) > 0:
        sims = np.dot(existing_embeddings, query_embedding)
        top_idx = int(np.argmax(sims))
        top_sim = float(sims[top_idx])
        if top_sim >= SEMANTIC_DUPLICATE_THRESHOLD:
            return existing_rows[top_idx][0], round(top_sim, 4), "semantic_similarity"

    return None


def ingest_questions(questions: list[RawQuestion], enable_semantic_dedup: bool = True) -> dict:
    """
    Ingest raw questions into the canonical question database with multi-level deduplication
    using the unified Topic field (no category, company, or platform fields).
    """
    stats = {
        "total_input": len(questions),
        "valid": 0,
        "new_canonical": 0,
        "duplicate_exact": 0,
        "duplicate_lexical": 0,
        "duplicate_semantic": 0,
        "sources_added": 0,
        "invalid": 0,
    }

    if not questions:
        return stats

    conn = _get_connection()
    try:
        now = time.time()

        cur_existing = conn.execute(
            "SELECT id, question_text, normalized_text FROM canonical_questions"
        )
        existing_rows: list[tuple[int, str, str]] = list(cur_existing.fetchall())

        valid_questions = [q for q in questions if validate_question(q)]
        stats["valid"] = len(valid_questions)
        stats["invalid"] = len(questions) - len(valid_questions)

        existing_embeddings = None
        new_embeddings_map: dict[int, np.ndarray] = {}

        if enable_semantic_dedup and valid_questions:
            try:
                from src.rag_assistant.embeddings import embed_texts
                if existing_rows:
                    existing_embeddings = embed_texts([r[1] for r in existing_rows])
                batch_embs = embed_texts([strip_html_markup(q.question_text) for q in valid_questions])
                for i, emb in enumerate(batch_embs):
                    new_embeddings_map[i] = emb
            except Exception as e:
                logger.warning(f"Semantic dedup embeddings unavailable, using lexical dedup only: {e}")

        for idx, raw in enumerate(valid_questions):
            clean_q = strip_html_markup(raw.question_text)
            clean_ref = strip_html_markup(raw.reference_answer or "")
            normalized_basic = normalize_text(clean_q)
            strict_norm = normalize_for_fingerprint(clean_q)
            fingerprint = compute_fingerprint(normalized_basic)
            strict_fp = compute_fingerprint(strict_norm)

            raw_topic = raw.topic.strip()
            c_topic, c_tech, c_tags = classify_question(clean_q, raw.interview_round)
            topic = normalize_topic(raw_topic, "", clean_q) if raw_topic else c_topic
            round_val = classify_round(clean_q, topic, raw.interview_round)
            is_tech = (topic != "Behavioral & HR") if raw_topic else c_tech
            tags = list(raw.tags or []) or c_tags

            # Level 1-3: Exact & normalized fingerprint match
            cursor = conn.execute(
                "SELECT id FROM canonical_questions WHERE fingerprint = ? OR fingerprint = ? OR normalized_text = ?",
                (fingerprint, strict_fp, strict_norm),
            )
            existing = cursor.fetchone()

            if existing:
                canonical_id = existing[0]
                stats["duplicate_exact"] += 1
                conn.execute(
                    "UPDATE canonical_questions SET frequency = COALESCE(frequency, 1) + 1, updated_at = ? WHERE id = ?",
                    (now, canonical_id),
                )
            else:
                q_emb = new_embeddings_map.get(idx)
                dup_match = _find_semantic_or_lexical_duplicate(
                    strict_norm, existing_rows, existing_embeddings, q_emb
                )

                if dup_match is not None:
                    canonical_id, sim_score, match_type = dup_match
                    if match_type == "lexical_near_duplicate":
                        stats["duplicate_lexical"] += 1
                    else:
                        stats["duplicate_semantic"] += 1

                    conn.execute(
                        "UPDATE canonical_questions SET frequency = COALESCE(frequency, 1) + 1, updated_at = ? WHERE id = ?",
                        (now, canonical_id),
                    )
                    conn.execute(
                        """
                        INSERT INTO question_duplicates
                            (canonical_id, duplicate_text, normalized_text, source_url, similarity_score, match_type, detected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            canonical_id, clean_q, strict_norm,
                            raw.source_url, sim_score, match_type, now,
                        ),
                    )
                else:
                    cursor = conn.execute(
                        """
                        INSERT INTO canonical_questions
                            (fingerprint, question_text, normalized_text, topic, difficulty,
                             question_type, is_technical, tags_json, frequency, reference_answer, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                        """,
                        (
                            fingerprint,
                            clean_q,
                            strict_norm,
                            topic,
                            raw.difficulty or "medium",
                            raw.question_type or ("hr" if round_val == "HR" else "open_ended"),
                            1 if is_tech else 0,
                            json.dumps(tags),
                            clean_ref,
                            now,
                            now,
                        ),
                    )
                    canonical_id = cursor.lastrowid
                    stats["new_canonical"] += 1

                    existing_rows.append((canonical_id, clean_q, strict_norm))
                    if q_emb is not None:
                        if existing_embeddings is None or len(existing_embeddings) == 0:
                            existing_embeddings = np.array([q_emb])
                        else:
                            existing_embeddings = np.vstack([existing_embeddings, q_emb])

            # Link source/round provenance idempotently
            cur_src = conn.execute(
                """
                SELECT id FROM question_sources
                WHERE canonical_id = ? AND interview_round = ? AND source_url = ?
                """,
                (canonical_id, round_val, raw.source_url),
            )
            if not cur_src.fetchone():
                conn.execute(
                    """
                    INSERT INTO question_sources
                        (canonical_id, source_url, role, interview_round, original_wording,
                         reported_at, collected_at, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        canonical_id,
                        raw.source_url,
                        raw.role,
                        round_val,
                        raw.original_wording or clean_q,
                        raw.reported_at,
                        raw.collected_at or now,
                        now,
                    ),
                )
                stats["sources_added"] += 1

        conn.commit()
        logger.info(
            f"Ingestion complete: {stats['new_canonical']} new, "
            f"{stats['duplicate_exact']} exact dupes, "
            f"{stats['duplicate_lexical']} lexical dupes, "
            f"{stats['duplicate_semantic']} semantic dupes, "
            f"{stats['sources_added']} sources added"
        )
    except Exception as e:
        conn.rollback()
        logger.error(f"Ingestion failed: {e}")
        raise
    finally:
        conn.close()

    return stats


def seed_curated_questions(curated_list: list[dict], replace_existing: bool = False) -> dict:
    """Seed the curated question bank into the canonical database."""
    if replace_existing:
        conn = _get_connection()
        try:
            conn.execute("DELETE FROM user_saved_questions")
            conn.execute("DELETE FROM question_duplicates")
            conn.execute("DELETE FROM question_sources")
            conn.execute("DELETE FROM canonical_questions")
            conn.commit()
        finally:
            conn.close()

    raw_questions = []
    now = time.time()
    for q in curated_list:
        q_text = strip_html_markup(q.get("question_text", ""))
        raw_topic = q.get("topic", "")
        topic = normalize_topic(raw_topic, "", q_text)
        round_val = classify_round(q_text, topic, q.get("round") or q.get("interview_round") or "")
        _, c_tech, c_tags = classify_question(q_text, round_val)
        is_tech = (topic != "Behavioral & HR") if raw_topic else c_tech
        tags = q.get("tags") or c_tags

        raw_questions.append(RawQuestion(
            question_text=q_text,
            source_url=q.get("source_url", ""),
            role="",
            interview_round=round_val,
            topic=topic,
            is_technical=is_tech,
            difficulty=(q.get("difficulty") or "medium").lower(),
            question_type="hr" if round_val == "HR" else "open_ended",
            reference_answer=strip_html_markup(q.get("reference_answer", "")),
            original_wording=q_text,
            tags=list(tags),
            collected_at=now,
        ))

    return ingest_questions(raw_questions, enable_semantic_dedup=False)


def get_canonical_question_count() -> int:
    """Get total number of canonical questions in the database."""
    conn = _get_connection()
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM canonical_questions")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_source_stats() -> dict:
    """Get summary counts of canonical questions and rounds."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            "SELECT interview_round, COUNT(DISTINCT canonical_id) FROM question_sources GROUP BY interview_round"
        )
        return {r[0] or "Technical": {"unique_questions": r[1]} for r in cur.fetchall()}
    finally:
        conn.close()
