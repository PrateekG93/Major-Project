"""
Session Manager
================
Manages user sessions after OTP verification.
Creates, validates, and invalidates session tokens using SQLite.
"""

import time
import uuid
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

SESSION_EXPIRY_SECONDS = 86400  # 24 hours


def create_session(email: str) -> str:
    """
    Create a new session token for an authenticated user.

    Args:
        email: Verified user email.

    Returns:
        Session token string.
    """
    from src.utils.checkpoint import _get_connection

    token = f"sess_{uuid.uuid4().hex}"
    now = time.time()
    expires_at = now + SESSION_EXPIRY_SECONDS

    conn = _get_connection()
    try:
        # Invalidate old sessions for this user
        conn.execute(
            "UPDATE user_sessions SET is_active = 0 WHERE email = ?",
            (email,),
        )

        # Create new session
        conn.execute(
            "INSERT INTO user_sessions (token, email, created_at, expires_at, is_active) VALUES (?, ?, ?, ?, 1)",
            (token, email, now, expires_at),
        )
        conn.commit()
        logger.info(f"Session created for {email}: {token[:16]}...")
        return token
    finally:
        conn.close()


def validate_session(token: str) -> Optional[str]:
    """
    Validate a session token.

    Args:
        token: Session token string.

    Returns:
        User email if valid, None otherwise.
    """
    from src.utils.checkpoint import _get_connection

    if not token:
        return None

    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT email, expires_at, is_active FROM user_sessions WHERE token = ?",
            (token,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        email, expires_at, is_active = row

        if not is_active or time.time() > expires_at:
            # Session expired or inactive
            conn.execute(
                "UPDATE user_sessions SET is_active = 0 WHERE token = ?", (token,)
            )
            conn.commit()
            return None

        return email
    finally:
        conn.close()


def logout(token: str) -> bool:
    """Invalidate a session token."""
    from src.utils.checkpoint import _get_connection

    conn = _get_connection()
    try:
        conn.execute(
            "UPDATE user_sessions SET is_active = 0 WHERE token = ?", (token,)
        )
        conn.commit()
        logger.info(f"Session logged out: {token[:16]}...")
        return True
    except Exception as e:
        logger.error(f"Failed to logout session: {e}")
        return False
    finally:
        conn.close()
