"""
OTP Manager
============
Cryptographically secure 6-digit OTP generation, HMAC-SHA256 hashed storage,
backend-enforced rate limiting / cooldowns / attempt lockouts, and SMTP email delivery.

Supports purposes: 'signup', 'login', 'password_reset'.
Supports OTP_MODE='email' (real SMTP) and OTP_MODE='console' (local dev terminal).
"""

import hashlib
import hmac
import os
import secrets
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

OTP_EXPIRY_SECONDS = int(os.getenv("OTP_EXPIRY_SECONDS", "300"))          # 5 minutes
OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN", "60"))  # 60 seconds
OTP_MAX_VERIFY_ATTEMPTS = int(os.getenv("OTP_MAX_VERIFY_ATTEMPTS", "5"))   # 5 wrong guesses max
OTP_MAX_RESENDS_PER_HOUR = int(os.getenv("OTP_MAX_RESENDS_PER_HOUR", "5")) # 5 sends/hour/purpose
OTP_RESET_TOKEN_EXPIRY = 600  # 10 minutes to complete password reset after OTP verified

VALID_PURPOSES = {"signup", "login", "password_reset"}


def _get_otp_secret() -> str:
    """Return server-side HMAC secret for OTP hashing."""
    return os.getenv("OTP_HMAC_SECRET", "copilot_otp_hmac_secret_2026_pr1107")


def _get_smtp_config() -> dict:
    """Read SMTP config fresh from .env (without clobbering runtime/test env overrides like SQLITE_DB_PATH)."""
    from dotenv import dotenv_values
    env_file = dotenv_values(".env") if os.path.exists(".env") else {}

    def _cfg(key: str, default: str = "") -> str:
        # Prefer explicit process env if set differently, or fresh .env value for runtime SMTP edits
        if key in os.environ and os.environ[key] != "":
            return os.environ[key]
        return str(env_file.get(key) or default)

    # For OTP_MODE & SMTP_* allow live .env reload when not explicitly overridden in tests
    mode = os.environ.get("OTP_MODE") or str(env_file.get("OTP_MODE") or "console")
    username = _cfg("SMTP_USERNAME") or _cfg("SMTP_EMAIL")
    from_email = _cfg("SMTP_FROM_EMAIL") or username
    return {
        "mode": mode.strip().lower(),
        "host": _cfg("SMTP_HOST", "smtp.gmail.com").strip(),
        "port": int(_cfg("SMTP_PORT", "587")),
        "username": username.strip(),
        "password": _cfg("SMTP_PASSWORD", "").strip(),
        "from_email": from_email.strip(),
        "from_name": _cfg("SMTP_FROM_NAME", "Academic & Career Copilot").strip(),
    }


def generate_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(email: str, purpose: str, otp_code: str) -> str:
    """Compute a salted HMAC-SHA256 hash of an OTP bound to email and purpose."""
    secret = _get_otp_secret().encode("utf-8")
    msg = f"{email.strip().lower()}:{purpose}:{otp_code.strip()}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def cleanup_expired_otps() -> int:
    """Delete expired or consumed OTP records older than 1 hour past expiry."""
    from src.utils.checkpoint import _get_connection

    conn = _get_connection()
    try:
        cutoff = time.time() - 3600
        cursor = conn.execute(
            "DELETE FROM otp_codes WHERE expires_at < ? OR (is_used = 1 AND created_at < ?)",
            (cutoff, cutoff),
        )
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        logger.warning(f"OTP cleanup error: {e}")
        return 0
    finally:
        conn.close()


def _check_cooldown_and_rate_limit(email: str, purpose: str) -> Optional[dict]:
    """
    Enforce 60-second resend cooldown and hourly send limit on backend.
    Returns None if allowed, or an error dict with 'message' and 'retry_after' if blocked.
    """
    from src.utils.checkpoint import _get_connection

    now = time.time()
    one_hour_ago = now - 3600
    conn = _get_connection()
    try:
        # Check most recent send time for cooldown
        cur_last = conn.execute(
            """
            SELECT last_sent_at, created_at
            FROM otp_codes
            WHERE email = ? AND purpose = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (email, purpose),
        )
        last_row = cur_last.fetchone()
        if last_row:
            last_ts = last_row[0] or last_row[1]
            elapsed = now - last_ts
            if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                wait_sec = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed) + 1
                return {
                    "success": False,
                    "message": f"Please wait {wait_sec} seconds before requesting another OTP.",
                    "retry_after": wait_sec,
                    "error_code": "cooldown",
                }

        # Check hourly rate limit
        cur_count = conn.execute(
            "SELECT COUNT(*) FROM otp_codes WHERE email = ? AND purpose = ? AND created_at > ?",
            (email, purpose, one_hour_ago),
        )
        count = cur_count.fetchone()[0]
        if count >= OTP_MAX_RESENDS_PER_HOUR:
            return {
                "success": False,
                "message": "Maximum OTP resend limit reached. Please wait an hour and try again.",
                "retry_after": 3600,
                "error_code": "rate_limit",
            }

        return None
    finally:
        conn.close()


def _store_otp_hash(email: str, purpose: str, otp_hash: str) -> None:
    """Invalidate previous unused OTPs for (email, purpose) and store the new OTP hash."""
    from src.utils.checkpoint import _get_connection

    conn = _get_connection()
    try:
        now = time.time()
        expires_at = now + OTP_EXPIRY_SECONDS

        # Count prior sends in last hour for resend_count tracking
        cur = conn.execute(
            "SELECT COUNT(*) FROM otp_codes WHERE email = ? AND purpose = ? AND created_at > ?",
            (email, purpose, now - 3600),
        )
        prior_sends = cur.fetchone()[0]

        # Invalidate previous unused OTPs for this email & purpose
        conn.execute(
            "UPDATE otp_codes SET is_used = 1 WHERE email = ? AND purpose = ? AND is_used = 0",
            (email, purpose),
        )

        # Store ONLY hash — never plaintext OTP
        conn.execute(
            """
            INSERT INTO otp_codes
                (email, otp_code, otp_hash, purpose, attempt_count, resend_count, last_sent_at, created_at, expires_at, is_used)
            VALUES (?, '[HASHED]', ?, ?, 0, ?, ?, ?, ?, 0)
            """,
            (email, otp_hash, purpose, prior_sends, now, now, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def _build_email_template(purpose: str, otp_code: str, from_name: str) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) tailored to OTP purpose."""
    purpose_meta = {
        "signup": (
            f"Verify Your {from_name} Account",
            "Account Email Verification",
            "Welcome! Enter the 6-digit verification code below to activate your account:",
        ),
        "login": (
            f"Your {from_name} Sign-In Code",
            "Secure Sign-In Verification",
            "Use the 6-digit one-time passcode below to complete your sign-in:",
        ),
        "password_reset": (
            f"{from_name} Password Reset Code",
            "Password Recovery Request",
            "Use the 6-digit verification code below to reset your account password:",
        ),
    }
    subject, heading, intro = purpose_meta.get(purpose, purpose_meta["login"])
    expiry_mins = max(1, OTP_EXPIRY_SECONDS // 60)

    text_body = (
        f"{from_name} — {heading}\n\n"
        f"{intro}\n\n"
        f"OTP Code: {otp_code}\n\n"
        f"This code expires in {expiry_mins} minutes and can only be used once.\n"
        f"Security Warning: Never share this code with anyone. If you did not request this, "
        f"you can safely ignore this email."
    )

    html_body = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 540px; margin: 0 auto; padding: 24px; background: #F5F2EC; color: #141413;">
        <div style="background: #141413; padding: 24px; border-radius: 8px 8px 0 0; text-align: center;">
            <div style="font-size: 11px; letter-spacing: 2px; color: #D9381E; text-transform: uppercase; font-weight: 700;">PR1107 // SECURITY DESK</div>
            <h2 style="margin: 6px 0 0; font-size: 22px; color: #F5F2EC;">{from_name}</h2>
            <p style="margin: 4px 0 0; font-size: 13px; color: #B5ACA0;">{heading}</p>
        </div>
        <div style="background: #FFFFFF; border: 1px solid #D8D1C5; border-top: none; border-radius: 0 0 8px 8px; padding: 28px 24px; text-align: center;">
            <p style="margin: 0 0 18px; color: #5A5852; font-size: 15px; line-height: 1.5;">{intro}</p>
            <div style="font-family: 'Courier New', monospace; font-size: 36px; font-weight: 700; letter-spacing: 10px; color: #141413;
                        padding: 16px 24px; background: #F5F2EC; border: 2px dashed #D9381E; border-radius: 6px;
                        margin: 16px auto; display: inline-block;">
                {otp_code}
            </div>
            <p style="color: #5A5852; font-size: 13px; margin: 18px 0 8px;">
                This code expires in <strong>{expiry_mins} minutes</strong> and is valid for a single use.
            </p>
            <div style="background: rgba(217, 56, 30, 0.06); border: 1px solid rgba(217, 56, 30, 0.2); border-radius: 4px; padding: 10px 14px; margin-top: 16px; text-align: left; font-size: 12px; color: #5A5852;">
                <strong>Security Warning:</strong> Never share this verification code with anyone. Our team will never ask for your OTP.
            </div>
        </div>
        <p style="text-align: center; color: #8A8780; font-size: 11px; margin-top: 16px;">
            If you did not request this verification code, please disregard this email or change your password immediately.
        </p>
    </body>
    </html>
    """
    return subject, html_body, text_body


def _send_email_otp(email: str, otp_code: str, purpose: str = "login") -> tuple[bool, str]:
    """Send OTP via configured SMTP server. Returns (sent, error_detail)."""
    cfg = _get_smtp_config()
    smtp_user = cfg["username"]
    smtp_password = cfg["password"]
    smtp_host = cfg["host"]
    smtp_port = cfg["port"]
    from_email = cfg["from_email"]
    from_name = cfg["from_name"]

    if not smtp_user or not smtp_password or not from_email:
        msg = "SMTP credentials not configured (SMTP_USERNAME/SMTP_PASSWORD/SMTP_FROM_EMAIL missing in .env)."
        logger.error(msg)
        return False, msg

    try:
        subject, html_body, text_body = _build_email_template(purpose, otp_code, from_name)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = email
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, email, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, email, msg.as_string())

        logger.info(f"OTP email ({purpose}) sent successfully to {email}")
        return True, ""
    except smtplib.SMTPAuthenticationError as e:
        err = (
            "SMTP authentication failed. For Gmail, enable 2FA and use a 16-character App Password "
            "in SMTP_PASSWORD."
        )
        logger.error(f"{err} ({e})")
        return False, err
    except Exception as e:
        err = f"Failed to deliver OTP email: {e}"
        logger.error(err)
        return False, err


def request_otp(email: str, purpose: str = "login") -> dict:
    """
    Generate, hash, store, and dispatch an OTP for ('signup' | 'login' | 'password_reset').
    Never exposes the OTP code in the API return payload when in email mode.
    """
    email = email.strip().lower()
    if purpose not in VALID_PURPOSES:
        return {"success": False, "message": "Invalid OTP purpose.", "error_code": "invalid_purpose"}

    if not email or "@" not in email:
        return {"success": False, "message": "Invalid email address.", "error_code": "invalid_email"}

    cleanup_expired_otps()

    blocked = _check_cooldown_and_rate_limit(email, purpose)
    if blocked:
        return blocked

    otp_code = generate_otp()
    otp_digest = hash_otp(email, purpose, otp_code)
    cfg = _get_smtp_config()

    if cfg["mode"] == "email":
        sent, err_detail = _send_email_otp(email, otp_code, purpose=purpose)
        if not sent:
            return {
                "success": False,
                "message": err_detail or "Failed to send OTP email. Check SMTP configuration.",
                "error_code": "smtp_failed",
            }
        _store_otp_hash(email, purpose, otp_digest)
        return {
            "success": True,
            "message": f"A 6-digit verification code has been sent to {email}. It expires in {OTP_EXPIRY_SECONDS // 60} minutes.",
            "cooldown_seconds": OTP_RESEND_COOLDOWN_SECONDS,
            "delivery_mode": "email",
        }
    else:
        _store_otp_hash(email, purpose, otp_digest)
        print(f"\n{'='*54}")
        print(f"  [CONSOLE OTP - {purpose.upper()}] {email} -> {otp_code}")
        print(f"{'='*54}\n")
        logger.info(f"[CONSOLE MODE] OTP ({purpose}) generated for {email}")
        return {
            "success": True,
            "message": f"Verification code generated in console mode (OTP_MODE=console). Check the backend server terminal.",
            "cooldown_seconds": OTP_RESEND_COOLDOWN_SECONDS,
            "delivery_mode": "console",
        }


def verify_otp(email: str, otp_code: str, purpose: str = "login", consume: bool = True) -> dict:
    """
    Verify an OTP against its stored hash with expiry, reuse, and max-attempt enforcement.
    """
    from src.utils.checkpoint import _get_connection

    email = email.strip().lower()
    otp_code = otp_code.strip()

    if purpose not in VALID_PURPOSES:
        return {"success": False, "message": "Invalid verification purpose."}

    if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
        return {"success": False, "message": "Please enter a valid 6-digit numeric OTP."}

    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT id, otp_hash, expires_at, is_used, COALESCE(attempt_count, 0)
            FROM otp_codes
            WHERE email = ? AND purpose = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (email, purpose),
        )
        row = cursor.fetchone()

        if not row:
            return {"success": False, "message": "No active OTP found. Please request a new code."}

        otp_id, stored_hash, expires_at, is_used, attempt_count = row
        now = time.time()

        if is_used:
            return {"success": False, "message": "This OTP has already been used or invalidated. Please request a new code."}

        if now > expires_at:
            conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp_id,))
            conn.commit()
            return {"success": False, "message": "This OTP has expired. Please request a new code."}

        if attempt_count >= OTP_MAX_VERIFY_ATTEMPTS:
            conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp_id,))
            conn.commit()
            return {"success": False, "message": "Maximum verification attempts exceeded. Please request a new OTP."}

        candidate_hash = hash_otp(email, purpose, otp_code)
        if not hmac.compare_digest(stored_hash, candidate_hash):
            new_attempts = attempt_count + 1
            invalidate = 1 if new_attempts >= OTP_MAX_VERIFY_ATTEMPTS else 0
            conn.execute(
                "UPDATE otp_codes SET attempt_count = ?, is_used = ? WHERE id = ?",
                (new_attempts, invalidate, otp_id),
            )
            conn.commit()
            remaining = max(0, OTP_MAX_VERIFY_ATTEMPTS - new_attempts)
            if remaining == 0:
                return {"success": False, "message": "Maximum verification attempts exceeded. This OTP is now locked."}
            return {"success": False, "message": f"Invalid OTP code. {remaining} attempt(s) remaining."}

        if consume:
            conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp_id,))
            conn.commit()

        logger.info(f"OTP verified ({purpose}) for {email} (consume={consume})")
        return {"success": True, "message": "OTP verified successfully."}
    finally:
        conn.close()
