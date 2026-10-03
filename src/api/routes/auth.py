"""
Auth Routes
=============
POST /api/v1/auth/signup       — Register with name, email, password
POST /api/v1/auth/signin       — Email+password login (admin → direct, student → OTP)
POST /api/v1/auth/request-otp  — Send OTP to email (fallback/resend)
POST /api/v1/auth/verify-otp   — Verify OTP, return session token
POST /api/v1/auth/logout       — Invalidate session
GET  /api/v1/auth/me           — Get current user from session token
"""

import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional

from src.auth.otp_manager import request_otp, verify_otp
from src.auth.session_manager import create_session, validate_session, logout
from src.utils.checkpoint import create_user, authenticate_user
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)
router = APIRouter()

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@copilot.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


# ---- Request / Response Models ----

class SignupRequest(BaseModel):
    name: str = Field(..., description="User full name")
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=4, description="Account password")


class SigninRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="Account password")


class OTPRequest(BaseModel):
    email: str = Field(..., description="User email address")


class OTPVerifyRequest(BaseModel):
    email: str = Field(..., description="User email address")
    otp: str = Field(..., description="6-digit OTP code")


class AuthResponse(BaseModel):
    success: bool
    message: str
    session_token: Optional[str] = None
    admin_token: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    is_admin: bool = False


# ---- Endpoints ----

@router.post("/auth/signup", response_model=AuthResponse)
async def api_signup(request: SignupRequest):
    """Register a new user with name, email, and password."""
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    if not request.email or "@" not in request.email:
        raise HTTPException(status_code=400, detail="Valid email is required.")
    if len(request.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")

    result = create_user(request.name, request.email, request.password)
    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["message"])

    return AuthResponse(
        success=True,
        message=result["message"],
    )


@router.post("/auth/signin", response_model=AuthResponse)
async def api_signin(request: SigninRequest):
    """
    Unified sign-in endpoint.
    - If admin credentials → returns admin_token directly (no OTP).
    - If regular user → verifies password then sends OTP to email.
    """
    email = request.email.strip().lower()

    # Check admin credentials first
    if email == ADMIN_EMAIL.lower() and request.password == ADMIN_PASSWORD:
        logger.info(f"Admin login: {email}")
        return AuthResponse(
            success=True,
            message="Admin login successful.",
            admin_token="admin_verified",
            email=email,
            is_admin=True,
        )

    # Regular user: verify password
    auth_result = authenticate_user(email, request.password)
    if not auth_result["success"]:
        raise HTTPException(status_code=401, detail=auth_result["message"])

    # Password OK → send OTP
    otp_result = request_otp(email)
    if not otp_result["success"]:
        raise HTTPException(status_code=500, detail=otp_result["message"])

    return AuthResponse(
        success=True,
        message=otp_result["message"],
        email=email,
        name=auth_result.get("name", ""),
        is_admin=False,
    )


@router.post("/auth/request-otp", response_model=AuthResponse)
async def api_request_otp(request: OTPRequest):
    """Send a 6-digit OTP to the provided email address (resend flow)."""
    result = request_otp(request.email)
    return AuthResponse(
        success=result["success"],
        message=result["message"],
    )


@router.post("/auth/verify-otp", response_model=AuthResponse)
async def api_verify_otp(request: OTPVerifyRequest):
    """Verify an OTP code and return a session token."""
    result = verify_otp(request.email, request.otp)

    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])

    # Create session
    token = create_session(request.email.strip().lower())

    return AuthResponse(
        success=True,
        message="Login successful.",
        session_token=token,
        email=request.email.strip().lower(),
    )


@router.post("/auth/logout", response_model=AuthResponse)
async def api_logout(x_session_token: Optional[str] = Header(None)):
    """Invalidate the current session."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="No session token provided")

    logout(x_session_token)
    return AuthResponse(success=True, message="Logged out successfully.")


@router.get("/auth/me", response_model=AuthResponse)
async def api_get_me(x_session_token: Optional[str] = Header(None)):
    """Get current user information from session token."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="No session token provided")

    email = validate_session(x_session_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return AuthResponse(
        success=True,
        message="Session valid.",
        email=email,
        session_token=x_session_token,
    )
