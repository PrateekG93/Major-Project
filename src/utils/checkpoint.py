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
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    # --- Original tables ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_checkpoints (
            session_id TEXT PRIMARY KEY,
            session_type TEXT NOT NULL,
            state_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS performance_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            score REAL NOT NULL,
            response_time REAL,
            features_json TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES session_checkpoints(session_id)
        )
    """)

    # --- Auth tables ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            password_hash TEXT DEFAULT '',
            created_at REAL NOT NULL,
            last_login REAL
        )
    """)

    # Migration: add password_hash column if missing (existing DB)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp_code TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            is_used INTEGER DEFAULT 0
        )
    """)
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
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(email, doc_type)
        )
    """)

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

    conn.commit()
    return conn


# ============================================================
# Original checkpoint functions (unchanged)
# ============================================================

def save_checkpoint(session_id: str, session_type: str, state: dict[str, Any]) -> None:
    """
    Save or update a session checkpoint.

    Args:
        session_id: Unique session identifier.
        session_type: Type of session ('interview', 'chat', etc.).
        state: Dictionary containing the full session state.
    """
    conn = _get_connection()
    try:
        now = time.time()
        state_json = json.dumps(state, default=str)
        conn.execute(
            """
            INSERT INTO session_checkpoints (session_id, session_type, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (session_id, session_type, state_json, now, now),
        )
        conn.commit()
        logger.info(f"Checkpoint saved for session {session_id}")
    except Exception as e:
        logger.error(f"Failed to save checkpoint for {session_id}: {e}")
        raise
    finally:
        conn.close()


def load_checkpoint(session_id: str) -> Optional[dict[str, Any]]:
    """
    Load a session checkpoint.

    Args:
        session_id: Unique session identifier.

    Returns:
        The session state dictionary, or None if not found.
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT state_json FROM session_checkpoints WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row:
            logger.info(f"Checkpoint loaded for session {session_id}")
            return json.loads(row[0])
        logger.warning(f"No checkpoint found for session {session_id}")
        return None
    except Exception as e:
        logger.error(f"Failed to load checkpoint for {session_id}: {e}")
        return None
    finally:
        conn.close()


def delete_checkpoint(session_id: str) -> bool:
    """Delete a session checkpoint."""
    conn = _get_connection()
    try:
        conn.execute(
            "DELETE FROM session_checkpoints WHERE session_id = ?", (session_id,)
        )
        conn.commit()
        logger.info(f"Checkpoint deleted for session {session_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete checkpoint for {session_id}: {e}")
        return False
    finally:
        conn.close()


def save_score(
    session_id: str,
    question_id: str,
    topic: str,
    score: float,
    response_time: Optional[float] = None,
    features: Optional[dict] = None,
) -> None:
    """
    Persist a single answer score to the relational database.

    Args:
        session_id: Interview session identifier.
        question_id: The question that was answered.
        topic: Topic category (e.g., 'Python', 'SQL').
        score: Normalized score between 0 and 1.
        response_time: Time taken to answer in seconds.
        features: Raw feature dictionary for debugging/analysis.
    """
    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO performance_scores
                (session_id, question_id, topic, score, response_time, features_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                question_id,
                topic,
                score,
                response_time,
                json.dumps(features) if features else None,
                time.time(),
            ),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to save score: {e}")
        raise
    finally:
        conn.close()


def get_session_scores(session_id: str) -> list[dict]:
    """Retrieve all scores for a session, ordered by creation time."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT question_id, topic, score, response_time, features_json, created_at
            FROM performance_scores
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        rows = cursor.fetchall()
        return [
            {
                "question_id": r[0],
                "topic": r[1],
                "score": r[2],
                "response_time": r[3],
                "features": json.loads(r[4]) if r[4] else None,
                "created_at": r[5],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_topic_averages(session_id: str) -> dict[str, float]:
    """
    Compute average score per topic for a given session.

    Returns:
        Dictionary mapping topic name to average score (0-100 scale).
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT topic, AVG(score) as avg_score
            FROM performance_scores
            WHERE session_id = ?
            GROUP BY topic
            """,
            (session_id,),
        )
        return {row[0]: round(row[1] * 100, 1) for row in cursor.fetchall()}
    finally:
        conn.close()


# ============================================================
# User document functions
# ============================================================

def save_user_document(email: str, doc_type: str, content_text: str, filename: str = "") -> None:
    """Save or update a user's document (resume or JD)."""
    conn = _get_connection()
    try:
        now = time.time()
        conn.execute(
            """
            INSERT INTO user_documents (email, doc_type, filename, content_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(email, doc_type) DO UPDATE SET
                filename = excluded.filename,
                content_text = excluded.content_text,
                updated_at = excluded.updated_at
            """,
            (email, doc_type, filename, content_text, now, now),
        )
        conn.commit()
        logger.info(f"Document '{doc_type}' saved for {email}")
    except Exception as e:
        logger.error(f"Failed to save document for {email}: {e}")
        raise
    finally:
        conn.close()


def get_user_document(email: str, doc_type: str) -> Optional[dict]:
    """Get a user's document by type ('resume' or 'jd')."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT filename, content_text, updated_at FROM user_documents WHERE email = ? AND doc_type = ?",
            (email, doc_type),
        )
        row = cursor.fetchone()
        if row:
            return {"filename": row[0], "content_text": row[1], "updated_at": row[2]}
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

def save_mcq_session(session_id: str, email: str, num_questions: int, state: dict) -> None:
    """Create or update an MCQ session."""
    conn = _get_connection()
    try:
        now = time.time()
        state_json = json.dumps(state, default=str)
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
        state_json = json.dumps(state, default=str)
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
                session_id, question_index, question_text,
                json.dumps(options), correct_answer, user_answer,
                1 if is_correct else 0, 1 if is_timeout else 0,
                response_time, topic, explanation, time.time(),
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
    """Get all registered users."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT email, name, created_at, last_login FROM users ORDER BY created_at DESC"
        )
        return [
            {"email": r[0], "name": r[1], "created_at": r[2], "last_login": r[3]}
            for r in cursor.fetchall()
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
    """Hash a password with SHA-256 + static salt (lightweight, no bcrypt dep)."""
    import hashlib
    salt = "copilot_salt_2026"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def create_user(name: str, email: str, password: str) -> dict:
    """
    Register a new user with name, email, and password.

    Returns:
        dict with 'success' and 'message'.
    """
    email = email.strip().lower()
    conn = _get_connection()
    try:
        # Check if already exists
        cursor = conn.execute("SELECT email FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            return {"success": False, "message": "An account with this email already exists. Please sign in."}

        now = time.time()
        pw_hash = _hash_password(password)
        conn.execute(
            "INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (email, name.strip(), pw_hash, now),
        )
        conn.commit()
        logger.info(f"User created: {email}")
        return {"success": True, "message": "Account created successfully! You can now sign in."}
    except Exception as e:
        logger.error(f"Failed to create user {email}: {e}")
        return {"success": False, "message": f"Registration failed: {str(e)}"}
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> dict:
    """
    Verify email + password.

    Returns:
        dict with 'success', 'message', and optionally 'name'.
    """
    email = email.strip().lower()
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT name, password_hash FROM users WHERE email = ?", (email,)
        )
        row = cursor.fetchone()
        if not row:
            return {"success": False, "message": "No account found with this email. Please sign up first."}

        stored_name, stored_hash = row
        if stored_hash != _hash_password(password):
            return {"success": False, "message": "Incorrect password."}

        # Update last login
        conn.execute("UPDATE users SET last_login = ? WHERE email = ?", (time.time(), email))
        conn.commit()

        return {"success": True, "message": "Authenticated.", "name": stored_name}
    finally:
        conn.close()
