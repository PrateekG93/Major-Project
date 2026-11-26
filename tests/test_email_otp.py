"""
Comprehensive Tests for Secure Email OTP Authentication (Task 3)
==================================================================
Covers: registration, bcrypt password hashing, HMAC-SHA256 OTP storage,
verification, login-before-verification block, invalid OTP & max attempts,
expired OTP, OTP reuse, 60s resend cooldown, max resend limit,
forgot-password enumeration protection, password reset & session invalidation.
"""

import os
import sqlite3
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def isolated_env(tmp_path):
    """Create isolated SQLite DB and console OTP mode for tests."""
    db_path = str(tmp_path / "test_auth.db")
    with patch.dict(
        os.environ,
        {
            "SQLITE_DB_PATH": db_path,
            "OTP_MODE": "console",
            "LOGIN_REQUIRE_OTP": "true",
            "OTP_HMAC_SECRET": "test_hmac_secret_key",
        },
    ):
        from src.utils.checkpoint import _get_connection
        conn = _get_connection()
        conn.close()
        yield db_path


def _extract_latest_otp_by_generating_known(email: str, purpose: str):
    """Helper to patch generate_otp deterministically when testing console mode."""
    return "482913"


def test_signup_otp_hash_and_login_before_verify(isolated_env):
    from src.api.main import app
    client = TestClient(app)

    with patch("src.auth.otp_manager.generate_otp", return_value="654321"):
        res = client.post(
            "/api/v1/auth/signup",
            json={
                "name": "Alice Student",
                "email": "alice@jklu.edu.in",
                "password": "Password123",
                "confirm_password": "Password123",
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["requires_verification"] is True
    assert "654321" not in data["message"]  # Never leak OTP in API response

    # Verify DB does NOT store plaintext password or plaintext OTP
    conn = sqlite3.connect(isolated_env)
    pw_hash, is_ver = conn.execute(
        "SELECT password_hash, is_verified FROM users WHERE email = ?", ("alice@jklu.edu.in",)
    ).fetchone()
    assert pw_hash.startswith("$2")  # bcrypt hash
    assert pw_hash != "Password123"
    assert is_ver == 0

    otp_code_col, otp_hash_col = conn.execute(
        "SELECT otp_code, otp_hash FROM otp_codes WHERE email = ?", ("alice@jklu.edu.in",)
    ).fetchone()
    assert otp_code_col == "[HASHED]"
    assert otp_hash_col != "654321"
    assert len(otp_hash_col) == 64
    conn.close()

    # Login before verification must be blocked (403)
    with patch("src.auth.otp_manager._check_cooldown_and_rate_limit", return_value=None):
        with patch("src.auth.otp_manager.generate_otp", return_value="654321"):
            signin_res = client.post(
                "/api/v1/auth/signin",
                json={"email": "alice@jklu.edu.in", "password": "Password123"},
            )
    assert signin_res.status_code == 403

    # Verify signup OTP activates account & returns session token
    ver_res = client.post(
        "/api/v1/auth/verify-signup",
        json={"email": "alice@jklu.edu.in", "otp": "654321", "purpose": "signup"},
    )
    assert ver_res.status_code == 200
    token = ver_res.json()["session_token"]
    assert token

    # OTP reuse must fail
    reuse_res = client.post(
        "/api/v1/auth/verify-signup",
        json={"email": "alice@jklu.edu.in", "otp": "654321", "purpose": "signup"},
    )
    assert reuse_res.status_code == 401

    # Protected route works with verified session
    me_res = client.get("/api/v1/auth/me", headers={"x-session-token": token})
    assert me_res.status_code == 200
    assert me_res.json()["is_verified"] is True


def test_otp_security_limits_attempts_cooldown_expiry_and_resends(isolated_env):
    from src.api.main import app
    client = TestClient(app)

    # 1. Signup
    with patch("src.auth.otp_manager.generate_otp", return_value="112233"):
        r = client.post(
            "/api/v1/auth/signup",
            json={
                "name": "Bob",
                "email": "bob@jklu.edu.in",
                "password": "Password123",
                "confirm_password": "Password123",
            },
        )
    assert r.status_code == 200

    # 2. 60-second resend cooldown enforced on backend
    cd_res = client.post(
        "/api/v1/auth/request-otp",
        json={"email": "bob@jklu.edu.in", "purpose": "signup"},
    )
    assert cd_res.status_code == 429

    # 3. 5 wrong attempts lock out the OTP
    for i in range(5):
        bad = client.post(
            "/api/v1/auth/verify-signup",
            json={"email": "bob@jklu.edu.in", "otp": "999999", "purpose": "signup"},
        )
        assert bad.status_code == 401

    # Even the right OTP is rejected once locked
    locked = client.post(
        "/api/v1/auth/verify-signup",
        json={"email": "bob@jklu.edu.in", "otp": "112233", "purpose": "signup"},
    )
    assert locked.status_code == 401
    assert "already been used" in locked.json()["detail"] or "Maximum" in locked.json()["detail"]

    # 4. Expired OTP rejected
    conn = sqlite3.connect(isolated_env)
    conn.execute("UPDATE otp_codes SET last_sent_at = ?", (time.time() - 120,))
    conn.commit()
    conn.close()

    with patch("src.auth.otp_manager.generate_otp", return_value="223344"):
        r2 = client.post(
            "/api/v1/auth/request-otp",
            json={"email": "bob@jklu.edu.in", "purpose": "signup"},
        )
    assert r2.status_code == 200

    conn = sqlite3.connect(isolated_env)
    conn.execute("UPDATE otp_codes SET expires_at = ? WHERE email = ? AND is_used = 0", (time.time() - 10, "bob@jklu.edu.in"))
    conn.commit()
    conn.close()

    exp_res = client.post(
        "/api/v1/auth/verify-signup",
        json={"email": "bob@jklu.edu.in", "otp": "223344", "purpose": "signup"},
    )
    assert exp_res.status_code == 401
    assert "expired" in exp_res.json()["detail"].lower()

    # 5. Max hourly resend limit (5) enforced
    for idx in range(3):
        conn = sqlite3.connect(isolated_env)
        conn.execute("UPDATE otp_codes SET last_sent_at = ?", (time.time() - 120,))
        conn.commit()
        conn.close()
        with patch("src.auth.otp_manager.generate_otp", return_value=f"33445{idx}"):
            res_ok = client.post(
                "/api/v1/auth/request-otp",
                json={"email": "bob@jklu.edu.in", "purpose": "signup"},
            )
            assert res_ok.status_code == 200

    # 6th request within the hour must be rejected with 429
    conn = sqlite3.connect(isolated_env)
    conn.execute("UPDATE otp_codes SET last_sent_at = ?", (time.time() - 120,))
    conn.commit()
    conn.close()
    res_limit = client.post(
        "/api/v1/auth/request-otp",
        json={"email": "bob@jklu.edu.in", "purpose": "signup"},
    )
    assert res_limit.status_code == 429


def test_forgot_password_reset_and_session_invalidation(isolated_env):
    from src.api.main import app
    client = TestClient(app)

    # Enumeration protection: nonexistent email returns 200 generic message
    enum_res = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nonexistent@jklu.edu.in"},
    )
    assert enum_res.status_code == 200

    # Create & verify user
    with patch("src.auth.otp_manager.generate_otp", return_value="101010"):
        client.post(
            "/api/v1/auth/signup",
            json={
                "name": "Carol",
                "email": "carol@jklu.edu.in",
                "password": "OldPassword1",
                "confirm_password": "OldPassword1",
            },
        )
    ver = client.post(
        "/api/v1/auth/verify-signup",
        json={"email": "carol@jklu.edu.in", "otp": "101010"},
    )
    old_token = ver.json()["session_token"]
    assert client.get("/api/v1/auth/me", headers={"x-session-token": old_token}).status_code == 200

    # Initiate forgot password
    with patch("src.auth.otp_manager.generate_otp", return_value="778899"):
        fp = client.post("/api/v1/auth/forgot-password", json={"email": "carol@jklu.edu.in"})
    assert fp.status_code == 200

    # Verify reset OTP (does not consume yet)
    vr = client.post(
        "/api/v1/auth/verify-reset-otp",
        json={"email": "carol@jklu.edu.in", "otp": "778899", "purpose": "password_reset"},
    )
    assert vr.status_code == 200

    # Complete password reset
    rp = client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": "carol@jklu.edu.in",
            "otp": "778899",
            "new_password": "NewPassword9",
            "confirm_password": "NewPassword9",
        },
    )
    assert rp.status_code == 200

    # Prior session MUST be invalidated!
    assert client.get("/api/v1/auth/me", headers={"x-session-token": old_token}).status_code == 401

    # Old password fails, new password works
    bad_login = client.post(
        "/api/v1/auth/signin",
        json={"email": "carol@jklu.edu.in", "password": "OldPassword1"},
    )
    assert bad_login.status_code == 401

    with patch("src.auth.otp_manager.generate_otp", return_value="556677"):
        good_login = client.post(
            "/api/v1/auth/signin",
            json={"email": "carol@jklu.edu.in", "password": "NewPassword9"},
        )
    assert good_login.status_code == 200
