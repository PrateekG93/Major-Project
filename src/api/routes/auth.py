"""
Auth Routes
=============
POST /api/v1/auth/signup           — Register with name, email, password & send verification OTP
POST /api/v1/auth/verify-signup    — Verify signup OTP, activate account, return session token
POST /api/v1/auth/signin           — Email+password login (admin → direct, verified student → OTP)
POST /api/v1/auth/request-otp      — Send/resend OTP (60s cooldown + max resend limit)
POST /api/v1/auth/verify-otp       — Verify login OTP, return session token
POST /api/v1/auth/forgot-password  — Initiate password reset (enumeration-safe)
POST /api/v1/auth/verify-reset-otp — Validate password reset OTP before new password entry
POST /api/v1/auth/reset-password   — Reset password with OTP, invalidate OTP & all active sessions
POST /api/v1/auth/logout           — Invalidate session
GET  /api/v1/auth/me               — Get current verified user from session token
"""

import os
import re
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from src.auth.dependencies import get_current_user
from src.auth.otp_manager import OTP_RESEND_COOLDOWN_SECONDS, request_otp, verify_otp
from src.auth.session_manager import (
    create_session,
    invalidate_all_user_sessions,
    logout,
)
from src.utils.checkpoint import (
    _get_connection,
    authenticate_user,
    create_user,
    is_user_verified,
    mark_user_verified,
    update_user_password,
    user_exists,
)
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)
router = APIRouter()

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@copilot.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def _validate_email_format(email: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$", email.strip()))


def _validate_password_strength(password: str) -> Optional[str]:
    """Return error message if password is weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None


# ---- Request / Response Models ----

class SignupRequest(BaseModel):
    name: str = Field(..., description="User full name")
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Account password (min 8 chars, letters + digits)")
    confirm_password: Optional[str] = Field(None, description="Confirm password")


class SigninRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="Account password")


class OTPRequest(BaseModel):
    email: str = Field(..., description="User email address")
    purpose: str = Field("login", description="OTP purpose: 'signup', 'login', or 'password_reset'")


class OTPVerifyRequest(BaseModel):
    email: str = Field(..., description="User email address")
    otp: str = Field(..., description="6-digit OTP code")
    purpose: str = Field("login", description="OTP purpose")


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="Registered email address")


class ResetPasswordRequest(BaseModel):
    email: str = Field(..., description="Registered email address")
    otp: str = Field(..., description="6-digit password reset OTP")
    new_password: str = Field(..., min_length=8, description="New strong password")
    confirm_password: Optional[str] = Field(None, description="Confirm new password")


class AuthResponse(BaseModel):
    success: bool
    message: str
    session_token: Optional[str] = None
    admin_token: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    is_admin: bool = False
    requires_verification: bool = False
    cooldown_seconds: Optional[int] = None
    delivery_mode: Optional[str] = None


# ---- Endpoints ----

@router.post("/auth/signup", response_model=AuthResponse)
async def api_signup(request: SignupRequest):
    """
    Register a new user (unverified) and dispatch a 6-digit email verification OTP.
    The account is activated only after OTP verification.
    """
    name = request.name.strip()
    email = request.email.strip().lower()

    if not name:
        raise HTTPException(status_code=400, detail="Full name is required.")
    if not _validate_email_format(email):
        raise HTTPException(status_code=400, detail="Valid email address is required.")
    if request.confirm_password is not None and request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    pw_err = _validate_password_strength(request.password)
    if pw_err:
        raise HTTPException(status_code=400, detail=pw_err)

    result = create_user(name, email, request.password, is_verified=False)
    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["message"])

    otp_result = request_otp(email, purpose="signup")
    if not otp_result["success"]:
        code = 429 if otp_result.get("error_code") in ("cooldown", "rate_limit") else 502
        raise HTTPException(status_code=code, detail=otp_result["message"])

    return AuthResponse(
        success=True,
        message=otp_result["message"],
        email=email,
        name=name,
        requires_verification=True,
        cooldown_seconds=otp_result.get("cooldown_seconds", OTP_RESEND_COOLDOWN_SECONDS),
        delivery_mode=otp_result.get("delivery_mode"),
    )


@router.post("/auth/verify-signup", response_model=AuthResponse)
async def api_verify_signup(request: OTPVerifyRequest):
    """Verify the signup email OTP, activate the user account, and return a session token."""
    email = request.email.strip().lower()
    if not user_exists(email):
        raise HTTPException(status_code=404, detail="No pending registration found for this email.")

    verify_res = verify_otp(email, request.otp, purpose="signup", consume=True)
    if not verify_res["success"]:
        raise HTTPException(status_code=401, detail=verify_res["message"])

    mark_user_verified(email)
    token = create_session(email)

    return AuthResponse(
        success=True,
        message="Email verified and account activated successfully.",
        session_token=token,
        email=email,
    )


@router.post("/auth/signin", response_model=AuthResponse)
async def api_signin(request: SigninRequest):
    """
    Unified sign-in endpoint.
    - Admin credentials -> returns admin_token directly.
    - Unverified student -> blocks login and indicates verification required.
    - Verified student -> dispatches login OTP (or returns session if LOGIN_REQUIRE_OTP=false).
    """
    email = request.email.strip().lower()

    if email == ADMIN_EMAIL.lower() and request.password == ADMIN_PASSWORD:
        logger.info(f"Admin login: {email}")
        return AuthResponse(
            success=True,
            message="Admin login successful.",
            admin_token="admin_verified",
            email=email,
            is_admin=True,
        )

    auth_result = authenticate_user(email, request.password)
    if not auth_result["success"]:
        if auth_result.get("requires_verification"):
            # Do not grant access; trigger/offer signup verification
            otp_res = request_otp(email, purpose="signup")
            msg = auth_result["message"]
            if otp_res.get("success"):
                msg = f"Email not verified. {otp_res['message']}"
            raise HTTPException(
                status_code=403,
                detail=msg,
                headers={"X-Requires-Verification": "true"},
            )
        raise HTTPException(status_code=401, detail=auth_result["message"])

    require_login_otp = os.getenv("LOGIN_REQUIRE_OTP", "true").strip().lower() != "false"
    if not require_login_otp:
        token = create_session(email)
        return AuthResponse(
            success=True,
            message="Sign-in successful.",
            session_token=token,
            email=email,
            name=auth_result.get("name", ""),
            is_admin=False,
        )

    otp_result = request_otp(email, purpose="login")
    if not otp_result["success"]:
        code = 429 if otp_result.get("error_code") in ("cooldown", "rate_limit") else 502
        raise HTTPException(status_code=code, detail=otp_result["message"])

    return AuthResponse(
        success=True,
        message=otp_result["message"],
        email=email,
        name=auth_result.get("name", ""),
        is_admin=False,
        cooldown_seconds=otp_result.get("cooldown_seconds", OTP_RESEND_COOLDOWN_SECONDS),
        delivery_mode=otp_result.get("delivery_mode"),
    )


@router.post("/auth/request-otp", response_model=AuthResponse)
async def api_request_otp(request: OTPRequest):
    """Send/resend a 6-digit OTP enforcing 60-second cooldown and max resend limits."""
    email = request.email.strip().lower()
    purpose = request.purpose.strip().lower()

    # For password_reset, avoid email enumeration
    if purpose == "password_reset" and not user_exists(email):
        return AuthResponse(
            success=True,
            message="If an account exists for that email, a verification code has been sent.",
            cooldown_seconds=OTP_RESEND_COOLDOWN_SECONDS,
        )

    result = request_otp(email, purpose=purpose)
    if not result["success"]:
        code = 429 if result.get("error_code") in ("cooldown", "rate_limit") else 400
        raise HTTPException(status_code=code, detail=result["message"])

    return AuthResponse(
        success=True,
        message=result["message"],
        email=email,
        cooldown_seconds=result.get("cooldown_seconds", OTP_RESEND_COOLDOWN_SECONDS),
        delivery_mode=result.get("delivery_mode"),
    )


@router.post("/auth/verify-otp", response_model=AuthResponse)
async def api_verify_otp(request: OTPVerifyRequest):
    """Verify an OTP code for login (or signup) and return a session token."""
    email = request.email.strip().lower()
    purpose = request.purpose.strip().lower()

    if purpose == "signup":
        return await api_verify_signup(request)

    if not is_user_verified(email):
        raise HTTPException(
            status_code=403,
            detail="Email address is not verified. Please complete email verification first.",
        )

    result = verify_otp(email, request.otp, purpose=purpose, consume=True)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])

    token = create_session(email)
    return AuthResponse(
        success=True,
        message="Login successful.",
        session_token=token,
        email=email,
    )


@router.post("/auth/forgot-password", response_model=AuthResponse)
async def api_forgot_password(request: ForgotPasswordRequest):
    """
    Initiate password recovery.
    Uses email enumeration protection (generic response whether email exists or not).
    """
    email = request.email.strip().lower()
    if not _validate_email_format(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    generic_msg = "If an account exists for that email address, a 6-digit password reset code has been sent."

    if not user_exists(email):
        return AuthResponse(
            success=True,
            message=generic_msg,
            cooldown_seconds=OTP_RESEND_COOLDOWN_SECONDS,
        )

    otp_result = request_otp(email, purpose="password_reset")
    if not otp_result["success"] and otp_result.get("error_code") in ("cooldown", "rate_limit"):
        raise HTTPException(status_code=429, detail=otp_result["message"])
    if not otp_result["success"]:
        raise HTTPException(status_code=502, detail=otp_result["message"])

    return AuthResponse(
        success=True,
        message=generic_msg if otp_result.get("delivery_mode") == "email" else otp_result["message"],
        email=email,
        cooldown_seconds=otp_result.get("cooldown_seconds", OTP_RESEND_COOLDOWN_SECONDS),
        delivery_mode=otp_result.get("delivery_mode"),
    )


@router.post("/auth/verify-reset-otp", response_model=AuthResponse)
async def api_verify_reset_otp(request: OTPVerifyRequest):
    """Validate password reset OTP (without consuming yet) before allowing new password input."""
    email = request.email.strip().lower()
    if not user_exists(email):
        raise HTTPException(status_code=401, detail="Invalid or expired OTP.")

    result = verify_otp(email, request.otp, purpose="password_reset", consume=False)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])

    return AuthResponse(
        success=True,
        message="Reset OTP verified. You may now set a new password.",
        email=email,
    )


@router.post("/auth/reset-password", response_model=AuthResponse)
async def api_reset_password(request: ResetPasswordRequest):
    """Verify & consume reset OTP, update password hash, and invalidate all active sessions."""
    email = request.email.strip().lower()

    if request.confirm_password is not None and request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    pw_err = _validate_password_strength(request.new_password)
    if pw_err:
        raise HTTPException(status_code=400, detail=pw_err)

    if not user_exists(email):
        raise HTTPException(status_code=401, detail="Invalid or expired password reset OTP.")

    result = verify_otp(email, request.otp, purpose="password_reset", consume=True)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])

    update_user_password(email, request.new_password)
    mark_user_verified(email)
    invalidate_all_user_sessions(email)

    logger.info(f"Password reset completed and sessions invalidated for {email}")
    return AuthResponse(
        success=True,
        message="Password has been reset successfully. Please sign in with your new password.",
        email=email,
    )


@router.post("/auth/logout", response_model=AuthResponse)
async def api_logout(x_session_token: Optional[str] = Header(None)):
    """Invalidate the current session."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="No session token provided")

    logout(x_session_token)
    return AuthResponse(success=True, message="Logged out successfully.")


@router.get("/auth/me")
async def api_me(email: str = Depends(get_current_user)):
    """Get current authenticated & verified user info."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            "SELECT name, COALESCE(is_verified, 1) FROM users WHERE email = ?",
            (email,),
        )
        row = cur.fetchone()
        name = row[0] if row else ""
        verified = bool(row[1]) if row else False
    finally:
        conn.close()

    return {"email": email, "name": name, "is_verified": verified}
