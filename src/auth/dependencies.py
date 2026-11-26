"""
FastAPI Authentication Dependencies
====================================
Reusable session validation dependencies enforcing verified-user access
on protected API endpoints.
"""

from typing import Optional
from fastapi import Header, HTTPException

from src.auth.session_manager import validate_session


def get_current_user(x_session_token: Optional[str] = Header(None)) -> str:
    """
    Require a valid, active session belonging to an email-verified user.
    Returns the authenticated user's email address.
    """
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Authentication required. Please sign in.")
    email = validate_session(x_session_token)
    if not email:
        raise HTTPException(
            status_code=401,
            detail="Invalid, expired, or unverified session. Please sign in again.",
        )
    return email


def get_optional_user(x_session_token: Optional[str] = Header(None)) -> Optional[str]:
    """Return authenticated user email if valid token provided, else None."""
    if not x_session_token:
        return None
    return validate_session(x_session_token)
