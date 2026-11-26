"""
Session Checkpoint Manager
==========================
Provides fault-tolerant session persistence using SQLite.
Serializes interview session state so users can resume after disconnection.
Also manages users, OTP codes, user sessions, and user documents.
"""

import json
import os
import sqlite3
import time
from typing import Any, Optional

from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

DB_PATH = os.getenv("SQLITE_DB_PATH", "./data/copilot_app.db")


def _get_connection() -> sqlite3.Connection:
    """Get a SQLite connection, creating the database and tables if needed."""
    db_path = os.getenv("SQLITE_DB_PATH", DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)

    # Remove deprecated viva checkpoint & scoring tables if present
    conn.execute("DROP TABLE IF EXISTS performance_scores")
    conn.execute("DROP TABLE IF EXISTS session_checkpoints")

    # --- Auth tables ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            password_hash TEXT DEFAULT '',
            is_verified INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            last_login REAL
        )
    """)

    # Migrations for existing users table
    for col_sql in [
        "ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 1",
    ]:
        try:
            conn.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.execute("""
        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp_code TEXT NOT NULL DEFAULT '[HASHED]',
            otp_hash TEXT DEFAULT '',
            purpose TEXT DEFAULT 'login',
            attempt_count INTEGER DEFAULT 0,
            resend_count INTEGER DEFAULT 0,
            last_sent_at REAL DEFAULT 0,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            is_used INTEGER DEFAULT 0
        )
    """)
    for col_sql in [
        "ALTER TABLE otp_codes ADD COLUMN otp_hash TEXT DEFAULT ''",
        "ALTER TABLE otp_codes ADD COLUMN purpose TEXT DEFAULT 'login'",
        "ALTER TABLE otp_codes ADD COLUMN attempt_count INTEGER DEFAULT 0",
        "ALTER TABLE otp_codes ADD COLUMN resend_count INTEGER DEFAULT 0",
        "ALTER TABLE otp_codes ADD COLUMN last_sent_at REAL DEFAULT 0",
    ]:
        try:
            conn.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            token TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (email) REFERENCES users(email)
        )
    """)

    # --- User documents (resume + JD per user) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            filename TEXT DEFAULT '',
            content_text TEXT NOT NULL,
            parsed_role TEXT DEFAULT '',
            parsed_company TEXT DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(email, doc_type)
        )
    """)
    for col_sql in [
        "ALTER TABLE user_documents ADD COLUMN parsed_role TEXT DEFAULT ''",
        "ALTER TABLE user_documents ADD COLUMN parsed_company TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # --- MCQ interview results ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mcq_sessions (
            session_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            num_questions INTEGER NOT NULL,
            total_correct INTEGER DEFAULT 0,
            total_answered INTEGER DEFAULT 0,
            state_json TEXT NOT NULL,
            is_complete INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (email) REFERENCES users(email)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mcq_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            options_json TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            user_answer TEXT,
            is_correct INTEGER DEFAULT 0,
            is_timeout INTEGER DEFAULT 0,
            response_time REAL,
            topic TEXT DEFAULT '',
            explanation TEXT DEFAULT '',
            created_at REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES mcq_sessions(session_id)
        )
    """)

    # --- Admin uploaded materials tracking ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_materials (
            doc_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            doc_type TEXT DEFAULT 'textbook',
            chunks_indexed INTEGER DEFAULT 0,
            uploaded_at REAL NOT NULL
        )
    """)

    # --- Dynamic Question Bank ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS canonical_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT UNIQUE NOT NULL,
            question_text TEXT NOT NULL,
            normalized_text TEXT DEFAULT '',
            topic TEXT DEFAULT '',
            difficulty TEXT DEFAULT 'medium',
            question_type TEXT DEFAULT 'open_ended',
            is_technical INTEGER DEFAULT 1,
            tags_json TEXT DEFAULT '[]',
            frequency INTEGER DEFAULT 1,
            reference_answer TEXT DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    for col_sql in [
        "ALTER TABLE canonical_questions ADD COLUMN normalized_text TEXT DEFAULT ''",
        "ALTER TABLE canonical_questions ADD COLUMN is_technical INTEGER DEFAULT 1",
        "ALTER TABLE canonical_questions ADD COLUMN tags_json TEXT DEFAULT '[]'",
        "ALTER TABLE canonical_questions ADD COLUMN frequency INTEGER DEFAULT 1",
    ]:
        try:
            conn.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Migrate legacy category column into topic and drop category
    try:
        cq_cols = [r[1] for r in conn.execute("PRAGMA table_info(canonical_questions)").fetchall()]
        if "category" in cq_cols:
            from src.interviewer.sources.classifier import normalize_topic
            rows = conn.execute("SELECT id, topic, category, question_text FROM canonical_questions").fetchall()
            for r_id, t_val, c_val, q_txt in rows:
                migrated_topic = normalize_topic(t_val or "", c_val or "", q_txt or "")
                conn.execute(
                    "UPDATE canonical_questions SET topic = ?, is_technical = ? WHERE id = ?",
                    (migrated_topic, 0 if migrated_topic == "Behavioral & HR" else 1, r_id),
                )
            conn.execute("ALTER TABLE canonical_questions DROP COLUMN category")
            conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS question_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_id INTEGER NOT NULL,
            source_url TEXT DEFAULT '',
            role TEXT DEFAULT '',
            interview_round TEXT DEFAULT 'Technical',
            original_wording TEXT DEFAULT '',
            reported_at TEXT DEFAULT '',
            collected_at REAL,
            scraped_at REAL NOT NULL,
            FOREIGN KEY (canonical_id) REFERENCES canonical_questions(id)
        )
    """)
    conn.execute("DROP INDEX IF EXISTS idx_qs_company")
    conn.execute("DROP INDEX IF EXISTS idx_qs_platform")
    try:
        qs_cols = [r[1] for r in conn.execute("PRAGMA table_info(question_sources)").fetchall()]
        for drop_col in ("company", "source_platform", "position"):
            if drop_col in qs_cols:
                conn.execute(f"ALTER TABLE question_sources DROP COLUMN {drop_col}")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS question_duplicates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_id INTEGER NOT NULL,
            duplicate_text TEXT NOT NULL,
            normalized_text TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            similarity_score REAL NOT NULL,
            match_type TEXT NOT NULL,
            detected_at REAL NOT NULL,
            FOREIGN KEY (canonical_id) REFERENCES canonical_questions(id)
        )
    """)
    try:
        qd_cols = [r[1] for r in conn.execute("PRAGMA table_info(question_duplicates)").fetchall()]
        if "source_platform" in qd_cols:
            conn.execute("ALTER TABLE question_duplicates DROP COLUMN source_platform")
            conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_saved_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            canonical_id INTEGER NOT NULL,
            notes TEXT DEFAULT '',
            created_at REAL NOT NULL,
            UNIQUE(email, canonical_id),
            FOREIGN KEY (canonical_id) REFERENCES canonical_questions(id),
            FOREIGN KEY (email) REFERENCES users(email)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS source_sync_status (
            source_name TEXT PRIMARY KEY,
            last_sync_at REAL,
            last_status TEXT DEFAULT 'never',
            questions_fetched INTEGER DEFAULT 0,
            questions_added INTEGER DEFAULT 0,
            duplicates_found INTEGER DEFAULT 0,
            error_message TEXT DEFAULT ''
        )
    """)
    try:
        ss_cols = [r[1] for r in conn.execute("PRAGMA table_info(source_sync_status)").fetchall()]
        if "source_platform" in ss_cols and "source_name" not in ss_cols:
            conn.execute("ALTER TABLE source_sync_status RENAME COLUMN source_platform TO source_name")
            conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS scraping_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL,
            topic TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            pages_scraped INTEGER DEFAULT 0,
            questions_found INTEGER DEFAULT 0,
            questions_new INTEGER DEFAULT 0,
            error_message TEXT DEFAULT '',
            started_at REAL,
            completed_at REAL,
            created_at REAL NOT NULL
        )
    """)
    try:
        sj_cols = [r[1] for r in conn.execute("PRAGMA table_info(scraping_jobs)").fetchall()]
        if "company" in sj_cols and "topic" not in sj_cols:
            conn.execute("ALTER TABLE scraping_jobs RENAME COLUMN company TO topic")
            conn.commit()
    except sqlite3.OperationalError:
        pass

    # --- Audio Interview Sessions & Turns ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audio_interview_sessions (
            session_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            company TEXT DEFAULT '',
            job_role TEXT NOT NULL,
            difficulty TEXT DEFAULT 'medium',
            interview_round TEXT DEFAULT 'Technical',
            max_questions INTEGER DEFAULT 5,
            max_duration_minutes INTEGER DEFAULT 20,
            scoring_weights_json TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            current_question_index INTEGER DEFAULT 0,
            followups_on_current INTEGER DEFAULT 0,
            current_question_json TEXT DEFAULT '{}',
            state_json TEXT NOT NULL,
            overall_score REAL,
            report_json TEXT DEFAULT '{}',
            started_at REAL NOT NULL,
            ended_at REAL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (email) REFERENCES users(email)
        )
    """)
    # Migrate existing audio_interview_sessions: drop legacy interview_type column if present
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(audio_interview_sessions)").fetchall()]
        if "interview_round" not in cols:
            conn.execute("ALTER TABLE audio_interview_sessions ADD COLUMN interview_round TEXT DEFAULT 'Technical'")
        if "interview_type" in cols:
            conn.execute("ALTER TABLE audio_interview_sessions DROP COLUMN interview_type")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS audio_interview_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL,
            is_followup INTEGER DEFAULT 0,
            parent_turn_index INTEGER,
            question_text TEXT NOT NULL,
            question_source TEXT DEFAULT 'question_bank',
            topic TEXT DEFAULT '',
            difficulty TEXT DEFAULT 'medium',
            audio_path TEXT DEFAULT '',
            audio_duration REAL DEFAULT 0.0,
            transcript TEXT DEFAULT '',
            stt_confidence REAL DEFAULT 1.0,
            fluency_json TEXT DEFAULT '{}',
            evaluation_json TEXT DEFAULT '{}',
            score REAL DEFAULT 0.0,
            next_action TEXT DEFAULT 'NEXT_QUESTION',
            reason_for_next TEXT DEFAULT '',
            created_at REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES audio_interview_sessions(session_id)
        )
    """)

    # Indexes for fast lookups
    conn.execute("CREATE INDEX IF NOT EXISTS idx_otp_email_purpose ON otp_codes(email, purpose)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_qs_round ON question_sources(interview_round)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cq_topic ON canonical_questions(topic)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cq_fingerprint ON canonical_questions(fingerprint)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cq_type ON canonical_questions(question_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_saved_email ON user_saved_questions(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_sess_email ON audio_interview_sessions(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_turns_sess ON audio_interview_turns(session_id)")

    conn.commit()
    _sanitize_stored_mcq_html(conn)
    return conn


def _sanitize_stored_mcq_html(conn: sqlite3.Connection) -> None:
    """Strip any legacy HTML tags/inline styles from stored MCQ questions, options, and explanations."""
    from src.utils.text_utils import contains_html_tag, strip_html_markup

    changed = False
    try:
        rows = conn.execute(
            "SELECT id, question_text, options_json, explanation FROM mcq_answers"
        ).fetchall()
        for row_id, q_text, opts_json, expl in rows:
            opts = json.loads(opts_json) if opts_json else []
            needs_fix = (
                contains_html_tag(q_text)
                or contains_html_tag(expl)
                or any(contains_html_tag(o) for o in opts)
            )
            if needs_fix:
                clean_q = strip_html_markup(q_text)
                clean_opts = [strip_html_markup(o) for o in opts]
                clean_expl = strip_html_markup(expl)
                conn.execute(
                    "UPDATE mcq_answers SET question_text = ?, options_json = ?, explanation = ? WHERE id = ?",
                    (clean_q, json.dumps(clean_opts), clean_expl, row_id),
                )
                changed = True

        s_rows = conn.execute("SELECT session_id, state_json FROM mcq_sessions").fetchall()
        for sid, state_json in s_rows:
            if not state_json or not contains_html_tag(state_json):
                continue
            state = json.loads(state_json)
            qs = state.get("questions", [])
            q_changed = False
            for q in qs:
                for fld in ("question_text", "explanation", "topic"):
                    if q.get(fld) and contains_html_tag(q[fld]):
                        q[fld] = strip_html_markup(q[fld])
                        q_changed = True
                if q.get("options") and any(contains_html_tag(o) for o in q["options"]):
                    q["options"] = [strip_html_markup(o) for o in q["options"]]
                    q_changed = True
            if q_changed:
                conn.execute(
                    "UPDATE mcq_sessions SET state_json = ? WHERE session_id = ?",
                    (json.dumps(state, default=str), sid),
                )
                changed = True

        if changed:
            conn.commit()
    except Exception as e:
        logger.warning(f"MCQ HTML sanitization check skipped: {e}")


# ============================================================
# User document functions
# ============================================================

def save_user_document(
    email: str,
    doc_type: str,
    content_text: str,
    filename: str = "",
    parsed_role: str = "",
    parsed_company: str = "",
) -> None:
    """Save or update a user's document (resume or JD) along with parsed dossier metadata."""
    conn = _get_connection()
    try:
        now = time.time()
        conn.execute(
            """
            INSERT INTO user_documents (
                email, doc_type, filename, content_text, parsed_role, parsed_company, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email, doc_type) DO UPDATE SET
                filename = excluded.filename,
                content_text = excluded.content_text,
                parsed_role = excluded.parsed_role,
                parsed_company = excluded.parsed_company,
                updated_at = excluded.updated_at
            """,
            (email, doc_type, filename, content_text, parsed_role, parsed_company, now, now),
        )
        conn.commit()
        logger.info(f"Document '{doc_type}' saved for {email}")
    except Exception as e:
        logger.error(f"Failed to save document for {email}: {e}")
        raise
    finally:
        conn.close()


def get_user_document(email: str, doc_type: str) -> Optional[dict]:
    """Get a user's document by type ('resume' or 'jd'), lazily parsing JD role/company if missing."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT filename, content_text, COALESCE(parsed_role, ''), COALESCE(parsed_company, ''), updated_at
            FROM user_documents WHERE email = ? AND doc_type = ?
            """,
            (email, doc_type),
        )
        row = cursor.fetchone()
        if row:
            filename, content_text, parsed_role, parsed_company, updated_at = row
            if doc_type == "jd" and (not parsed_role):
                try:
                    from src.interviewer.role_matcher import parse_jd_metadata
                    parsed_role, parsed_company = parse_jd_metadata(content_text, filename)
                    conn.execute(
                        "UPDATE user_documents SET parsed_role = ?, parsed_company = ? WHERE email = ? AND doc_type = ?",
                        (parsed_role, parsed_company, email, doc_type),
                    )
                    conn.commit()
                except Exception:
                    pass
            return {
                "filename": filename,
                "content_text": content_text,
                "parsed_role": parsed_role,
                "parsed_company": parsed_company,
                "updated_at": updated_at,
            }
        return None
    finally:
        conn.close()


def get_user_documents(email: str) -> dict:
    """Get both resume and JD for a user."""
    return {
        "resume": get_user_document(email, "resume"),
        "jd": get_user_document(email, "jd"),
    }


# ============================================================
# MCQ session functions
# ============================================================

def _clean_mcq_state(state: dict) -> dict:
    """Return a copy of MCQ session state with all HTML markup stripped from questions and options."""
    from src.utils.text_utils import strip_html_markup

    cleaned_state = dict(state)
    qs = []
    for q in state.get("questions", []):
        qc = dict(q)
        qc["question_text"] = strip_html_markup(qc.get("question_text", ""))
        qc["options"] = [strip_html_markup(o) for o in qc.get("options", [])]
        if qc.get("explanation"):
            qc["explanation"] = strip_html_markup(qc["explanation"])
        qs.append(qc)
    cleaned_state["questions"] = qs
    return cleaned_state


def save_mcq_session(session_id: str, email: str, num_questions: int, state: dict) -> None:
    """Create or update an MCQ session."""
    conn = _get_connection()
    try:
        now = time.time()
        state_json = json.dumps(_clean_mcq_state(state), default=str)
        conn.execute(
            """
            INSERT INTO mcq_sessions (session_id, email, num_questions, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                state_json = excluded.state_json,
                total_correct = excluded.total_correct,
                total_answered = excluded.total_answered,
                is_complete = excluded.is_complete,
                updated_at = excluded.updated_at
            """,
            (session_id, email, num_questions, state_json, now, now),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to save MCQ session: {e}")
        raise
    finally:
        conn.close()


def update_mcq_session(session_id: str, total_correct: int, total_answered: int, is_complete: bool, state: dict) -> None:
    """Update MCQ session progress."""
    conn = _get_connection()
    try:
        now = time.time()
        state_json = json.dumps(_clean_mcq_state(state), default=str)
        conn.execute(
            """
            UPDATE mcq_sessions SET
                total_correct = ?, total_answered = ?, is_complete = ?,
                state_json = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (total_correct, total_answered, 1 if is_complete else 0, state_json, now, session_id),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to update MCQ session: {e}")
        raise
    finally:
        conn.close()


def save_mcq_answer(
    session_id: str, question_index: int, question_text: str,
    options: list[str], correct_answer: str, user_answer: str,
    is_correct: bool, is_timeout: bool, response_time: float,
    topic: str = "", explanation: str = "",
) -> None:
    """Save a single MCQ answer."""
    from src.utils.text_utils import strip_html_markup
    clean_q = strip_html_markup(question_text)
    clean_opts = [strip_html_markup(o) for o in options]
    clean_expl = strip_html_markup(explanation)
    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO mcq_answers (
                session_id, question_index, question_text, options_json,
                correct_answer, user_answer, is_correct, is_timeout,
                response_time, topic, explanation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, question_index, clean_q,
                json.dumps(clean_opts), correct_answer, user_answer,
                1 if is_correct else 0, 1 if is_timeout else 0,
                response_time, strip_html_markup(topic), clean_expl, time.time(),
            ),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to save MCQ answer: {e}")
        raise
    finally:
        conn.close()


def get_mcq_session(session_id: str) -> Optional[dict]:
    """Load an MCQ session."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT session_id, email, num_questions, total_correct, total_answered, is_complete, state_json, created_at FROM mcq_sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "session_id": row[0], "email": row[1], "num_questions": row[2],
                "total_correct": row[3], "total_answered": row[4],
                "is_complete": bool(row[5]), "state": json.loads(row[6]),
                "created_at": row[7],
            }
        return None
    finally:
        conn.close()


def get_mcq_answers(session_id: str) -> list[dict]:
    """Get all answers for an MCQ session."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT question_index, question_text, options_json, correct_answer,
                   user_answer, is_correct, is_timeout, response_time, topic, explanation
            FROM mcq_answers WHERE session_id = ? ORDER BY question_index ASC
            """,
            (session_id,),
        )
        return [
            {
                "question_index": r[0], "question_text": r[1],
                "options": json.loads(r[2]), "correct_answer": r[3],
                "user_answer": r[4], "is_correct": bool(r[5]),
                "is_timeout": bool(r[6]), "response_time": r[7],
                "topic": r[8], "explanation": r[9],
            }
            for r in cursor.fetchall()
        ]
    finally:
        conn.close()


def get_user_mcq_sessions(email: str) -> list[dict]:
    """Get all MCQ sessions for a user."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT session_id, num_questions, total_correct, total_answered, is_complete, created_at
            FROM mcq_sessions WHERE email = ? ORDER BY created_at DESC
            """,
            (email,),
        )
        return [
            {
                "session_id": r[0], "num_questions": r[1], "total_correct": r[2],
                "total_answered": r[3], "is_complete": bool(r[4]), "created_at": r[5],
            }
            for r in cursor.fetchall()
        ]
    finally:
        conn.close()


def get_latest_mcq_session(email: str) -> Optional[dict]:
    """Get the most recent completed MCQ session for a user."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT session_id, num_questions, total_correct, total_answered, is_complete, state_json, created_at
            FROM mcq_sessions WHERE email = ? AND is_complete = 1
            ORDER BY created_at DESC LIMIT 1
            """,
            (email,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "session_id": row[0], "num_questions": row[1], "total_correct": row[2],
                "total_answered": row[3], "is_complete": bool(row[4]),
                "state": json.loads(row[5]), "created_at": row[6],
            }
        return None
    finally:
        conn.close()


# ============================================================
# Admin materials functions
# ============================================================

def save_admin_material(doc_id: str, filename: str, doc_type: str, chunks_indexed: int) -> None:
    """Track an admin-uploaded material."""
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO admin_materials (doc_id, filename, doc_type, chunks_indexed, uploaded_at) VALUES (?, ?, ?, ?, ?)",
            (doc_id, filename, doc_type, chunks_indexed, time.time()),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to save admin material: {e}")
        raise
    finally:
        conn.close()


def get_admin_materials() -> list[dict]:
    """List all admin-uploaded materials."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT doc_id, filename, doc_type, chunks_indexed, uploaded_at FROM admin_materials ORDER BY uploaded_at DESC"
        )
        return [
            {"doc_id": r[0], "filename": r[1], "doc_type": r[2], "chunks_indexed": r[3], "uploaded_at": r[4]}
            for r in cursor.fetchall()
        ]
    finally:
        conn.close()


def delete_admin_material(doc_id: str) -> bool:
    """Delete an admin material record."""
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM admin_materials WHERE doc_id = ?", (doc_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to delete admin material: {e}")
        return False
    finally:
        conn.close()


# ============================================================
# User management functions (for admin)
# ============================================================

def get_all_users() -> list[dict]:
    """Get all registered users with verification status and uploaded dossier metadata."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT u.email, u.name, u.is_verified, u.created_at, u.last_login,
                   MAX(CASE WHEN d.doc_type = 'resume' THEN 1 ELSE 0 END) AS has_resume,
                   MAX(CASE WHEN d.doc_type = 'jd' THEN 1 ELSE 0 END) AS has_jd,
                   MAX(CASE WHEN d.doc_type = 'jd' THEN COALESCE(d.parsed_role, '') ELSE '' END) AS jd_role,
                   MAX(CASE WHEN d.doc_type = 'jd' THEN COALESCE(d.parsed_company, '') ELSE '' END) AS jd_company
            FROM users u
            LEFT JOIN user_documents d ON LOWER(u.email) = LOWER(d.email)
            GROUP BY u.email, u.name, u.is_verified, u.created_at, u.last_login
            ORDER BY u.created_at DESC
            """
        )
        return [
            {
                "email": r[0],
                "name": r[1],
                "is_verified": bool(r[2]) if r[2] is not None else False,
                "created_at": r[3],
                "last_login": r[4],
                "has_resume": bool(r[5]),
                "has_jd": bool(r[6]),
                "jd_role": r[7] or "",
                "jd_company": r[8] or "",
            }
            for r in cursor.fetchall()
        ]
    finally:
        conn.close()


def get_all_audio_results() -> list[dict]:
    """Get all adaptive AI audio interview sessions across all users (for admin)."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            """
            SELECT session_id, email, company, job_role, interview_round, difficulty,
                   status, questions_asked, followups_asked, total_score, grade,
                   started_at, completed_at
            FROM audio_interview_sessions
            ORDER BY started_at DESC
            """
        ).fetchall()
        return [
            {
                "session_id": r[0],
                "email": r[1],
                "company": r[2] or "",
                "job_role": r[3] or "Software Engineer",
                "interview_round": r[4] or "Technical",
                "difficulty": r[5] or "medium",
                "status": r[6] or "active",
                "questions_asked": r[7] or 0,
                "followups_asked": r[8] or 0,
                "total_score": r[9] or 0.0,
                "grade": r[10] or "N/A",
                "started_at": r[11],
                "completed_at": r[12],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_all_mcq_results() -> list[dict]:
    """Get all MCQ results across all users (for admin)."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT s.session_id, s.email, s.num_questions, s.total_correct,
                   s.total_answered, s.is_complete, s.created_at
            FROM mcq_sessions s
            ORDER BY s.created_at DESC
            """
        )
        return [
            {
                "session_id": r[0], "email": r[1], "num_questions": r[2],
                "total_correct": r[3], "total_answered": r[4],
                "is_complete": bool(r[5]), "created_at": r[6],
            }
            for r in cursor.fetchall()
        ]
    finally:
        conn.close()


# ============================================================
# Signup / password authentication helpers
# ============================================================

def _hash_password(password: str) -> str:
    """Hash a password securely using bcrypt (falls back to salted PBKDF2 if unavailable)."""
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    except ImportError:
        import hashlib
        import secrets
        salt = secrets.token_hex(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return f"pbkdf2${salt}${dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """
    Verify password against stored hash.
    Returns (is_valid, needs_rehash).
    Supports bcrypt, PBKDF2, and legacy SHA-256 hashes (migrating legacy hashes on login).
    """
    if not stored_hash:
        return False, False

    if stored_hash.startswith("$2"):
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")), False
        except Exception:
            return False, False

    if stored_hash.startswith("pbkdf2$"):
        import hashlib
        import hmac
        parts = stored_hash.split("$", 2)
        if len(parts) != 3:
            return False, False
        _, salt, expected_hex = parts
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return hmac.compare_digest(dk.hex(), expected_hex), False

    # Legacy SHA-256 check
    import hashlib
    import hmac
    legacy_hash = hashlib.sha256(f"copilot_salt_2026{password}".encode()).hexdigest()
    is_valid = hmac.compare_digest(stored_hash, legacy_hash)
    return is_valid, is_valid


def create_user(name: str, email: str, password: str, is_verified: bool = False) -> dict:
    """
    Register a new user with name, email, and password.
    New registrations default to is_verified=False until email OTP verification succeeds.
    """
    email = email.strip().lower()
    conn = _get_connection()
    try:
        cursor = conn.execute("SELECT email, is_verified FROM users WHERE email = ?", (email,))
        existing = cursor.fetchone()
        if existing:
            if not existing[1]:
                # Unverified account re-registering: update name/password so user can complete verification
                pw_hash = _hash_password(password)
                conn.execute(
                    "UPDATE users SET name = ?, password_hash = ? WHERE email = ?",
                    (name.strip(), pw_hash, email),
                )
                conn.commit()
                return {
                    "success": True,
                    "requires_verification": True,
                    "message": "Account pending verification. A verification OTP will be sent to your email.",
                }
            return {"success": False, "message": "An account with this email already exists. Please sign in."}

        now = time.time()
        pw_hash = _hash_password(password)
        conn.execute(
            "INSERT INTO users (email, name, password_hash, is_verified, created_at) VALUES (?, ?, ?, ?, ?)",
            (email, name.strip(), pw_hash, 1 if is_verified else 0, now),
        )
        conn.commit()
        logger.info(f"User created (verified={is_verified}): {email}")
        return {
            "success": True,
            "requires_verification": not is_verified,
            "message": "Account created! Please verify your email with the 6-digit OTP sent to you." if not is_verified else "Account created successfully!",
        }
    except Exception as e:
        logger.error(f"Failed to create user {email}: {e}")
        return {"success": False, "message": f"Registration failed: {str(e)}"}
    finally:
        conn.close()


def mark_user_verified(email: str) -> bool:
    """Mark a user's email as verified."""
    email = email.strip().lower()
    conn = _get_connection()
    try:
        cursor = conn.execute("UPDATE users SET is_verified = 1 WHERE email = ?", (email,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def is_user_verified(email: str) -> bool:
    """Return True if user exists and has verified their email."""
    email = email.strip().lower()
    conn = _get_connection()
    try:
        cursor = conn.execute("SELECT is_verified FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return bool(row and row[0])
    finally:
        conn.close()


def user_exists(email: str) -> bool:
    """Return True if an account exists for the given email."""
    email = email.strip().lower()
    conn = _get_connection()
    try:
        cursor = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,))
        return cursor.fetchone() is not None
    finally:
        conn.close()


def update_user_password(email: str, new_password: str) -> bool:
    """Update a user's password hash securely."""
    email = email.strip().lower()
    pw_hash = _hash_password(new_password)
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ? WHERE email = ?",
            (pw_hash, email),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> dict:
    """
    Verify email + password and verification status.

    Returns:
        dict with 'success', 'message', 'is_verified', and optionally 'name'.
    """
    email = email.strip().lower()
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT name, password_hash, is_verified FROM users WHERE email = ?", (email,)
        )
        row = cursor.fetchone()
        if not row:
            return {"success": False, "message": "Invalid email or password.", "is_verified": False}

        stored_name, stored_hash, verified_flag = row
        is_valid, needs_rehash = _verify_password(password, stored_hash)
        if not is_valid:
            return {"success": False, "message": "Invalid email or password.", "is_verified": bool(verified_flag)}

        if needs_rehash:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE email = ?",
                (_hash_password(password), email),
            )

        if not verified_flag:
            conn.commit()
            return {
                "success": False,
                "requires_verification": True,
                "is_verified": False,
                "name": stored_name,
                "message": "Email address not verified. Please verify your account with the OTP sent to your email.",
            }

        # Update last login
        conn.execute("UPDATE users SET last_login = ? WHERE email = ?", (time.time(), email))
        conn.commit()

        return {"success": True, "message": "Authenticated.", "name": stored_name, "is_verified": True}
    finally:
        conn.close()
