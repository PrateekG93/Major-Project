"""
Question Bank Search, Filtering, Topic Browsing & Bookmarking Service
======================================================================
Provides structured querying across canonical_questions, question_sources,
question_duplicates, and user_saved_questions (by Topic, Round, Difficulty).
"""

import json
import random
import time
from typing import Optional

from src.interviewer.role_matcher import get_jd_question_bank_topics
from src.interviewer.sources.classifier import FIXED_ROUNDS, FIXED_TOPICS
from src.utils.checkpoint import _get_connection, get_user_document
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_user_jd_context(user_email: Optional[str]) -> dict:
    """Resolve the candidate's uploaded JD and matching Question Bank domains."""
    if not user_email:
        return {"has_jd": False, "jd_role": "", "jd_company": "", "jd_topics": []}
    try:
        jd_doc = get_user_document(user_email, "jd")
    except Exception:
        jd_doc = None
    if not jd_doc or not (jd_doc.get("content_text") or jd_doc.get("parsed_role")):
        return {"has_jd": False, "jd_role": "", "jd_company": "", "jd_topics": []}

    jd_text = jd_doc.get("content_text", "")
    jd_role = jd_doc.get("parsed_role", "") or ""
    jd_company = jd_doc.get("parsed_company", "") or ""
    jd_topics = get_jd_question_bank_topics(jd_text, jd_role)
    return {
        "has_jd": True,
        "jd_role": jd_role,
        "jd_company": jd_company,
        "jd_topics": jd_topics,
    }


def search_questions(
    q: str = "",
    role: str = "",
    interview_round: str = "",
    difficulty: str = "",
    topic: str = "",
    is_technical: Optional[bool] = None,
    sort_by: str = "relevance",  # relevance | recent | frequency
    page: int = 1,
    page_size: int = 15,
    user_email: Optional[str] = None,
    bookmarked_only: bool = False,
    scope: str = "jd",  # 'jd' (JD-related questions first) | 'all' (all domains)
) -> dict:
    """
    Search and filter canonical interview questions with sorting and pagination.
    When an authenticated user has uploaded a JD and scope='jd' (default),
    returns JD-relevant domains first unless 'all' or an explicit topic is chosen.
    """
    jd_ctx = get_user_jd_context(user_email)
    jd_topics = jd_ctx["jd_topics"]
    clean_scope = "all" if str(scope).strip().lower() == "all" else "jd"
    jd_filter_active = (
        clean_scope == "jd"
        and bool(jd_topics)
        and not topic.strip()
        and not bookmarked_only
    )

    conn = _get_connection()
    try:
        where_clauses = ["1=1"]
        params: list = []

        if q.strip():
            term = f"%{q.strip()}%"
            where_clauses.append(
                "(cq.question_text LIKE ? OR cq.topic LIKE ? OR cq.tags_json LIKE ? OR cq.reference_answer LIKE ?)"
            )
            params.extend([term, term, term, term])

        if role.strip():
            where_clauses.append("qs.role LIKE ?")
            params.append(f"%{role.strip()}%")

        if interview_round.strip():
            where_clauses.append("LOWER(qs.interview_round) = ?")
            params.append(interview_round.strip().lower())

        if difficulty.strip():
            where_clauses.append("LOWER(cq.difficulty) = ?")
            params.append(difficulty.strip().lower())

        if topic.strip():
            where_clauses.append("LOWER(cq.topic) = ?")
            params.append(topic.strip().lower())
        elif jd_filter_active:
            placeholders = ",".join("?" * len(jd_topics))
            where_clauses.append(f"cq.topic IN ({placeholders})")
            params.extend(jd_topics)

        if is_technical is not None:
            where_clauses.append("COALESCE(cq.is_technical, 1) = ?")
            params.append(1 if is_technical else 0)

        join_bookmark = ""
        if bookmarked_only and user_email:
            join_bookmark = "INNER JOIN user_saved_questions usq ON cq.id = usq.canonical_id AND usq.email = ?"
            params_prefix = [user_email]
        else:
            params_prefix = []

        where_sql = " AND ".join(where_clauses)

        count_sql = f"""
            SELECT COUNT(DISTINCT cq.id)
            FROM canonical_questions cq
            LEFT JOIN question_sources qs ON cq.id = qs.canonical_id
            {join_bookmark}
            WHERE {where_sql}
        """
        total = conn.execute(count_sql, params_prefix + params).fetchone()[0]

        order_params: list = []
        jd_case_sql = ""
        if jd_topics and sort_by == "relevance":
            when_parts = []
            for rank_idx, jt in enumerate(jd_topics):
                when_parts.append("WHEN LOWER(cq.topic) = ? THEN ?")
                order_params.extend([jt.lower(), rank_idx])
            jd_case_sql = f"CASE {' '.join(when_parts)} ELSE {len(jd_topics)} END, "

        if sort_by == "recent":
            order_sql = "cq.updated_at DESC, cq.id DESC"
        elif sort_by == "frequency":
            order_sql = "COALESCE(cq.frequency, 1) DESC, cq.updated_at DESC"
        else:
            if q.strip():
                order_sql = (
                    f"{jd_case_sql}"
                    "CASE WHEN LOWER(cq.question_text) LIKE ? THEN 0 ELSE 1 END, "
                    "COALESCE(cq.frequency, 1) DESC, cq.id DESC"
                )
            else:
                order_sql = f"{jd_case_sql}COALESCE(cq.frequency, 1) DESC, cq.created_at DESC"

        offset = (max(1, page) - 1) * page_size

        data_sql = f"""
            SELECT DISTINCT cq.id, cq.question_text, cq.topic, cq.difficulty,
                   cq.question_type, COALESCE(cq.is_technical, 1), COALESCE(cq.tags_json, '[]'),
                   COALESCE(cq.frequency, 1), cq.reference_answer, cq.created_at, cq.updated_at
            FROM canonical_questions cq
            LEFT JOIN question_sources qs ON cq.id = qs.canonical_id
            {join_bookmark}
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
        """

        query_params = params_prefix + params + order_params
        if sort_by == "relevance" and q.strip():
            query_params.append(f"%{q.strip().lower()}%")
        query_params.extend([page_size, offset])

        rows = conn.execute(data_sql, query_params).fetchall()

        bookmarked_ids: set[int] = set()
        if user_email:
            b_cur = conn.execute(
                "SELECT canonical_id FROM user_saved_questions WHERE email = ?",
                (user_email,),
            )
            bookmarked_ids = {r[0] for r in b_cur.fetchall()}

        items = []
        for r in rows:
            cid = r[0]
            src_rows = conn.execute(
                """
                SELECT source_url, role, interview_round, reported_at, collected_at
                FROM question_sources
                WHERE canonical_id = ?
                ORDER BY scraped_at DESC
                """,
                (cid,),
            ).fetchall()

            sources = [
                {
                    "source_url": sr[0] or "",
                    "role": sr[1] or "",
                    "interview_round": sr[2] or "",
                    "reported_at": sr[3] or "",
                    "collected_at": sr[4],
                }
                for sr in src_rows
            ]

            dup_count = conn.execute(
                "SELECT COUNT(*) FROM question_duplicates WHERE canonical_id = ?",
                (cid,),
            ).fetchone()[0]

            try:
                tags = json.loads(r[6]) if r[6] else []
            except Exception:
                tags = []

            rounds = sorted({s["interview_round"] for s in sources if s["interview_round"]})

            items.append({
                "id": cid,
                "question_text": r[1],
                "topic": r[2] or "Data Structures & Algorithms",
                "difficulty": r[3] or "medium",
                "question_type": r[4] or "open_ended",
                "is_technical": bool(r[5]),
                "tags": tags,
                "frequency": r[7],
                "reference_answer": r[8] or "",
                "created_at": r[9],
                "updated_at": r[10],
                "rounds": rounds,
                "sources": sources,
                "duplicate_variations_count": dup_count,
                "is_bookmarked": cid in bookmarked_ids,
            })

        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "items": items,
            "jd_context": {
                **jd_ctx,
                "active_scope": "jd" if jd_filter_active else "all",
            },
        }
    finally:
        conn.close()


def get_topics_catalog(user_email: Optional[str] = None) -> list[dict]:
    """Return all topics in the question bank with counts, prioritizing JD-matched domains first."""
    jd_ctx = get_user_jd_context(user_email)
    jd_topics = jd_ctx["jd_topics"]
    jd_rank = {t: i for i, t in enumerate(jd_topics)}

    conn = _get_connection()
    try:
        rows = conn.execute(
            """
            SELECT cq.topic,
                   COUNT(DISTINCT cq.id) as total_q,
                   COUNT(DISTINCT CASE WHEN LOWER(cq.difficulty) = 'easy' THEN cq.id END) as easy_q,
                   COUNT(DISTINCT CASE WHEN LOWER(cq.difficulty) = 'medium' THEN cq.id END) as med_q,
                   COUNT(DISTINCT CASE WHEN LOWER(cq.difficulty) = 'hard' THEN cq.id END) as hard_q,
                   GROUP_CONCAT(DISTINCT qs.interview_round) as rounds
            FROM canonical_questions cq
            LEFT JOIN question_sources qs ON cq.id = qs.canonical_id
            WHERE cq.topic != ''
            GROUP BY cq.topic
            ORDER BY cq.topic ASC
            """
        ).fetchall()

        order_map = {t: i for i, t in enumerate(FIXED_TOPICS)}
        catalog = [
            {
                "topic": r[0],
                "question_count": r[1],
                "easy_count": r[2],
                "medium_count": r[3],
                "hard_count": r[4],
                "rounds": sorted({rnd for rnd in (r[5] or "").split(",") if rnd}),
                "is_jd_match": r[0] in jd_rank,
            }
            for r in rows
        ]
        catalog.sort(key=lambda x: (0 if x["is_jd_match"] else 1, jd_rank.get(x["topic"], 999), order_map.get(x["topic"], 999), x["topic"]))
        return catalog
    finally:
        conn.close()


def get_filter_facets(user_email: Optional[str] = None) -> dict:
    """Return distinct facet values for search filters (Topic, Round, Difficulty) and JD context."""
    jd_ctx = get_user_jd_context(user_email)
    jd_topics = jd_ctx["jd_topics"]
    conn = _get_connection()
    try:
        db_topics = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT topic FROM canonical_questions WHERE topic != '' ORDER BY topic"
            ).fetchall()
        ]
        base_topics = [t for t in FIXED_TOPICS if t in db_topics] + [
            t for t in db_topics if t not in FIXED_TOPICS
        ]
        # List JD-matched domains first when available
        ordered_topics = [t for t in jd_topics if t in base_topics] + [
            t for t in base_topics if t not in jd_topics
        ]
        return {
            "topics": ordered_topics or list(FIXED_TOPICS),
            "rounds": list(FIXED_ROUNDS),
            "difficulties": ["easy", "medium", "hard"],
            "jd_context": jd_ctx,
        }
    finally:
        conn.close()


def retrieve_questions_by_topic(
    topics: list[str],
    num_questions: int = 10,
    difficulty_mix: Optional[dict] = None,
    question_type: str = "open_ended",
    exclude_ids: Optional[set[int]] = None,
) -> list[dict]:
    """Retrieve diverse questions from canonical_questions matching the requested topics."""
    topics = topics or list(FIXED_TOPICS[:3])
    exclude_ids = exclude_ids or set()
    conn = _get_connection()
    try:
        topic_clauses = " OR ".join(["cq.topic LIKE ?"] * len(topics))
        params: list = [f"%{t}%" for t in topics]
        query = f"""
            SELECT DISTINCT cq.id, cq.question_text, cq.topic, cq.difficulty,
                   cq.question_type, cq.reference_answer, qs.interview_round
            FROM canonical_questions cq
            LEFT JOIN question_sources qs ON cq.id = qs.canonical_id
            WHERE ({topic_clauses}) AND cq.question_type = ?
        """
        params.append(question_type)
        if exclude_ids:
            placeholders = ",".join("?" * len(exclude_ids))
            query += f" AND cq.id NOT IN ({placeholders})"
            params.extend(exclude_ids)
        query += " ORDER BY RANDOM() LIMIT ?"
        params.append(max(num_questions * 3, 30))

        rows = conn.execute(query, params).fetchall()
        candidates = [
            {
                "canonical_id": r[0],
                "question_text": r[1],
                "topic": r[2],
                "difficulty": r[3],
                "question_type": r[4],
                "reference_answer": r[5],
                "interview_round": r[6] or "Technical",
            }
            for r in rows
        ]
    finally:
        conn.close()

    if difficulty_mix:
        selected = []
        seen = set()
        for diff, cnt in difficulty_mix.items():
            pool = [c for c in candidates if c["difficulty"] == diff and c["canonical_id"] not in seen]
            random.shuffle(pool)
            for item in pool[:cnt]:
                selected.append(item)
                seen.add(item["canonical_id"])
        for c in candidates:
            if len(selected) >= num_questions:
                break
            if c["canonical_id"] not in seen:
                selected.append(c)
                seen.add(c["canonical_id"])
        random.shuffle(selected)
        return selected[:num_questions]

    random.shuffle(candidates)
    return candidates[:num_questions]


def bookmark_question(email: str, canonical_id: int, notes: str = "") -> bool:
    """Save/bookmark a question for a user."""
    conn = _get_connection()
    try:
        exists = conn.execute("SELECT 1 FROM canonical_questions WHERE id = ?", (canonical_id,)).fetchone()
        if not exists:
            return False
        conn.execute(
            """
            INSERT INTO user_saved_questions (email, canonical_id, notes, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email, canonical_id) DO UPDATE SET notes = excluded.notes
            """,
            (email.strip().lower(), canonical_id, notes, time.time()),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def remove_bookmark(email: str, canonical_id: int) -> bool:
    """Remove a bookmarked question for a user."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM user_saved_questions WHERE email = ? AND canonical_id = ?",
            (email.strip().lower(), canonical_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_duplicate_relationships(canonical_id: Optional[int] = None, limit: int = 50) -> list[dict]:
    """Retrieve recorded duplicate relationships and similarity scores."""
    conn = _get_connection()
    try:
        if canonical_id is not None:
            rows = conn.execute(
                """
                SELECT d.id, d.canonical_id, cq.question_text, d.duplicate_text,
                       d.source_url, d.similarity_score, d.match_type, d.detected_at
                FROM question_duplicates d
                JOIN canonical_questions cq ON d.canonical_id = cq.id
                WHERE d.canonical_id = ?
                ORDER BY d.detected_at DESC LIMIT ?
                """,
                (canonical_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT d.id, d.canonical_id, cq.question_text, d.duplicate_text,
                       d.source_url, d.similarity_score, d.match_type, d.detected_at
                FROM question_duplicates d
                JOIN canonical_questions cq ON d.canonical_id = cq.id
                ORDER BY d.detected_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "id": r[0],
                "canonical_id": r[1],
                "canonical_question": r[2],
                "duplicate_text": r[3],
                "source_url": r[4],
                "similarity_score": r[5],
                "match_type": r[6],
                "detected_at": r[7],
            }
            for r in rows
        ]
    finally:
        conn.close()
