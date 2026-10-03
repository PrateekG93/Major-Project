"""
OTP Manager
============
Generates, stores, and verifies 6-digit OTP codes.
Supports console mode (dev) and email mode (production).
"""

import os
import random
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

OTP_MODE = os.getenv("OTP_MODE", "console")  # 'console' or 'email'
OTP_EXPIRY_SECONDS = 300  # 5 minutes
OTP_MAX_ATTEMPTS_PER_HOUR = 5

# SMTP settings (only used when OTP_MODE='email')
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")


def generate_otp() -> str:
    """Generate a random 6-digit OTP."""
    return str(random.randint(100000, 999999))


def _store_otp(email: str, otp_code: str) -> None:
    """Store OTP in database with expiry."""
    import sqlite3
    from src.utils.checkpoint import _get_connection

    conn = _get_connection()
    try:
        now = time.time()
        expires_at = now + OTP_EXPIRY_SECONDS

        # Invalidate previous unused OTPs for this email
        conn.execute(
            "UPDATE otp_codes SET is_used = 1 WHERE email = ? AND is_used = 0",
            (email,),
        )

        # Insert new OTP
        conn.execute(
            "INSERT INTO otp_codes (email, otp_code, created_at, expires_at, is_used) VALUES (?, ?, ?, ?, 0)",
            (email, otp_code, now, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def _check_rate_limit(email: str) -> bool:
    """Check if user has exceeded OTP request rate limit."""
    from src.utils.checkpoint import _get_connection

    conn = _get_connection()
    try:
        one_hour_ago = time.time() - 3600
        cursor = conn.execute(
            "SELECT COUNT(*) FROM otp_codes WHERE email = ? AND created_at > ?",
            (email, one_hour_ago),
        )
        count = cursor.fetchone()[0]
        return count < OTP_MAX_ATTEMPTS_PER_HOUR
    finally:
        conn.close()


def _send_email_otp(email: str, otp_code: str) -> bool:
    """Send OTP via email using SMTP."""
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        logger.error("SMTP credentials not configured. Set SMTP_EMAIL and SMTP_PASSWORD in .env")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎓 Academic Copilot - Your Login OTP: {otp_code}"
        msg["From"] = SMTP_EMAIL
        msg["To"] = email

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; color: white;">
                <h2>🎓 Academic & Career Copilot</h2>
            </div>
            <div style="padding: 30px 20px; text-align: center;">
                <p>Your one-time login code is:</p>
                <div style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #667eea; padding: 20px; background: #f5f5f5; border-radius: 10px; margin: 20px 0;">
                    {otp_code}
                </div>
                <p style="color: #888; font-size: 14px;">This code expires in 5 minutes. Do not share it.</p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, email, msg.as_string())

        logger.info(f"OTP email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {e}")
        return False


def request_otp(email: str) -> dict:
    """
    Generate and send an OTP to the given email.

    Returns:
        dict with 'success' flag and 'message'.
    """
    email = email.strip().lower()

    if not email or "@" not in email:
        return {"success": False, "message": "Invalid email address."}

    # Rate limit check
    if not _check_rate_limit(email):
        return {"success": False, "message": "Too many OTP requests. Please wait and try again."}

    otp_code = generate_otp()
    _store_otp(email, otp_code)

    if OTP_MODE == "email":
        sent = _send_email_otp(email, otp_code)
        if not sent:
            # Fallback to console
            logger.warning(f"Email send failed, falling back to console. OTP for {email}: {otp_code}")
            print(f"\n{'='*50}")
            print(f"  OTP for {email}: {otp_code}")
            print(f"{'='*50}\n")
    else:
        # Console mode — print OTP to server terminal
        print(f"\n{'='*50}")
        print(f"  OTP for {email}: {otp_code}")
        print(f"{'='*50}\n")
        logger.info(f"[CONSOLE MODE] OTP for {email}: {otp_code}")

    return {"success": True, "message": f"OTP sent to {email}. Check your {'inbox' if OTP_MODE == 'email' else 'server console'}."}


def verify_otp(email: str, otp_code: str) -> dict:
    """
    Verify an OTP code.

    Returns:
        dict with 'success' flag and 'message'.
    """
    from src.utils.checkpoint import _get_connection

    email = email.strip().lower()
    conn = _get_connection()
    try:
        now = time.time()
        cursor = conn.execute(
            """
            SELECT id, otp_code, expires_at FROM otp_codes
            WHERE email = ? AND is_used = 0
            ORDER BY created_at DESC LIMIT 1
            """,
            (email,),
        )
        row = cursor.fetchone()

        if not row:
            return {"success": False, "message": "No pending OTP found. Please request a new one."}

        otp_id, stored_otp, expires_at = row

        if now > expires_at:
            # Mark as used
            conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp_id,))
            conn.commit()
            return {"success": False, "message": "OTP has expired. Please request a new one."}

        if otp_code != stored_otp:
            return {"success": False, "message": "Invalid OTP. Please try again."}

        # Mark OTP as used
        conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp_id,))

        # Create or update user record
        conn.execute(
            """
            INSERT INTO users (email, created_at, last_login)
            VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET last_login = excluded.last_login
            """,
            (email, now, now),
        )
        conn.commit()

        logger.info(f"OTP verified for {email}")
        return {"success": True, "message": "OTP verified successfully."}
    finally:
        conn.close()
