"""
Login / Signup View
=====================
Two-panel auth screen inspired by the provided UI mockup:

LEFT panel (coloured)  ←→ RIGHT panel (form)
Toggles between "Sign In" and "Sign Up" modes.

Sign In flow:
  1. Email + Password  → click SIGN IN
     - If admin credentials → redirect to admin portal
     - If student → OTP sent to email → enter OTP → VERIFY → logged in

Sign Up flow:
  Name + Email + Password → click SIGN UP → account created → switch to Sign In
"""

import requests
import streamlit as st


def render():
    # -------- Premium CSS for the two-panel card --------
    st.markdown("""
    <style>
        /* Hide Streamlit header / footer for a clean login page */
        header[data-testid="stHeader"] {visibility: hidden;}
        .block-container {padding-top: 1.5rem !important;}

        /* Hero card wrapper */
        .auth-card {
            max-width: 820px;
            margin: 20px auto;
            border-radius: 24px;
            overflow: hidden;
            box-shadow: 0 25px 80px rgba(102, 126, 234, 0.20), 0 8px 20px rgba(0,0,0,0.08);
            border: 1px solid rgba(255,255,255,0.35);
        }

        /* Side panel (welcome / hello) */
        .auth-side {
            background: linear-gradient(145deg, #b85450 0%, #8b3a3a 100%);
            padding: 50px 35px;
            text-align: center;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            min-height: 360px;
            border-radius: 24px;
        }
        .auth-side h2 {
            color: #fff; font-size: 2em; font-weight: 700;
            margin-bottom: 12px;
        }
        .auth-side p {
            color: rgba(255,255,255,0.82); font-size: 0.95em; margin-bottom: 22px;
        }

        /* Form area heading */
        .form-heading {
            text-align: center; font-size: 1.75em; font-weight: 700;
            margin-bottom: 18px; color: #1a1a2e;
        }

        /* OTP large-letter input */
        .otp-input input {
            font-size: 24px !important; letter-spacing: 8px !important;
            text-align: center !important; font-weight: bold !important;
        }

        /* Section divider */
        .auth-divider {
            border: 0; border-top: 1px solid #e0e0e0; margin: 18px 0;
        }
    </style>
    """, unsafe_allow_html=True)

    # -------- Session-state defaults --------
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "signin"  # 'signin' or 'signup'
    if "otp_step" not in st.session_state:
        st.session_state.otp_step = False  # True once OTP sent
    if "signin_email" not in st.session_state:
        st.session_state.signin_email = ""

    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")

    # ================================================================
    #  SIGN UP MODE
    # ================================================================
    if st.session_state.auth_mode == "signup":
        left_col, right_col = st.columns([5, 5], gap="small")

        # ---- Right panel: Signup form ----
        with left_col:
            st.markdown('<p class="form-heading">Create Account</p>', unsafe_allow_html=True)

            with st.form("signup_form"):
                name = st.text_input("👤 Name", placeholder="Full Name", key="su_name")
                email = st.text_input("📧 Email", placeholder="you@example.com", key="su_email")
                password = st.text_input("🔒 Password", type="password", placeholder="••••••••", key="su_pass")
                signup_btn = st.form_submit_button("SIGN UP", type="primary", use_container_width=True)

            if signup_btn:
                if not name.strip():
                    st.error("Name is required.")
                elif not email or "@" not in email:
                    st.error("Enter a valid email address.")
                elif len(password) < 4:
                    st.error("Password must be at least 4 characters.")
                else:
                    with st.spinner("Creating account…"):
                        try:
                            resp = requests.post(
                                f"{api_base}/api/v1/auth/signup",
                                json={"name": name, "email": email, "password": password},
                                timeout=15,
                            )
                            if resp.status_code == 200:
                                st.success("✅ " + resp.json().get("message", "Account created!"))
                                st.session_state.auth_mode = "signin"
                                st.session_state.otp_step = False
                                st.rerun()
                            else:
                                st.error(f"❌ {resp.json().get('detail', 'Signup failed')}")
                        except requests.ConnectionError:
                            st.error(
                                "❌ Cannot connect to the API server. "
                                "Make sure the backend is running:\n"
                                "```\npython -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload\n```"
                            )
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

        # ---- Left panel: Welcome banner ----
        with right_col:
            st.markdown("""
            <div class="auth-side">
                <h2>Welcome User!</h2>
                <p>If you already have an account</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("SIGN IN", key="go_signin", use_container_width=True, type="secondary"):
                st.session_state.auth_mode = "signin"
                st.session_state.otp_step = False
                st.rerun()

    # ================================================================
    #  SIGN IN MODE
    # ================================================================
    else:
        left_col, right_col = st.columns([5, 5], gap="small")

        # ---- Left panel: Sign-in form ----
        with left_col:
            st.markdown('<p class="form-heading">Sign In</p>', unsafe_allow_html=True)

            # -- Step 1: Email + Password --
            if not st.session_state.otp_step:
                with st.form("signin_form"):
                    email = st.text_input("📧 Email", placeholder="you@example.com", key="si_email")
                    password = st.text_input("🔒 Password", type="password", placeholder="••••••••", key="si_pass")
                    signin_btn = st.form_submit_button("SIGN IN", type="primary", use_container_width=True)

                if signin_btn:
                    if not email or "@" not in email:
                        st.error("Enter a valid email address.")
                    elif not password:
                        st.error("Enter your password.")
                    else:
                        with st.spinner("Signing in…"):
                            try:
                                resp = requests.post(
                                    f"{api_base}/api/v1/auth/signin",
                                    json={"email": email, "password": password},
                                    timeout=15,
                                )
                                if resp.status_code == 200:
                                    data = resp.json()
                                    if data.get("is_admin"):
                                        # Admin → go directly to admin portal
                                        st.session_state.admin_token = data["admin_token"]
                                        st.session_state.admin_mode = True
                                        st.success("✅ Admin login successful!")
                                        st.rerun()
                                    else:
                                        # Student → OTP sent, show OTP entry
                                        st.session_state.signin_email = email.strip().lower()
                                        st.session_state.otp_step = True
                                        st.success(f"✅ {data.get('message', 'OTP sent!')}")
                                        st.rerun()
                                else:
                                    st.error(f"❌ {resp.json().get('detail', 'Login failed')}")
                            except requests.ConnectionError:
                                st.error(
                                    "❌ Cannot connect to the API server. "
                                    "Make sure the backend is running:\n"
                                    "```\npython -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload\n```"
                                )
                            except Exception as e:
                                st.error(f"Error: {str(e)}")

            # -- Step 2: OTP verification --
            else:
                st.info(f"📧 OTP sent to **{st.session_state.signin_email}**")
                st.caption("Check your **email inbox** (or server console if using console mode).")

                with st.form("otp_form"):
                    otp = st.text_input(
                        "🔐 Enter 6-digit OTP",
                        max_chars=6,
                        placeholder="______",
                        key="otp_input",
                    )
                    col_a, col_b = st.columns([2, 1])
                    with col_a:
                        verify_btn = st.form_submit_button("VERIFY & LOGIN ✅", type="primary", use_container_width=True)
                    with col_b:
                        resend_btn = st.form_submit_button("Resend OTP", use_container_width=True)

                if verify_btn:
                    if not otp or len(otp) != 6:
                        st.error("Enter the full 6-digit OTP.")
                    else:
                        with st.spinner("Verifying…"):
                            try:
                                resp = requests.post(
                                    f"{api_base}/api/v1/auth/verify-otp",
                                    json={"email": st.session_state.signin_email, "otp": otp},
                                    timeout=15,
                                )
                                if resp.status_code == 200:
                                    data = resp.json()
                                    st.session_state.session_token = data["session_token"]
                                    st.session_state.user_email = data["email"]
                                    st.session_state.otp_step = False
                                    st.session_state.auth_mode = "signin"
                                    st.success("✅ Login successful!")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {resp.json().get('detail', 'Verification failed')}")
                            except requests.ConnectionError:
                                st.error("Cannot connect to the API server.")
                            except Exception as e:
                                st.error(f"Error: {str(e)}")

                if resend_btn:
                    try:
                        resp = requests.post(
                            f"{api_base}/api/v1/auth/request-otp",
                            json={"email": st.session_state.signin_email},
                            timeout=15,
                        )
                        if resp.status_code == 200:
                            st.success("New OTP sent! Check your inbox / console.")
                        else:
                            st.error("Failed to resend OTP.")
                    except Exception:
                        st.error("Cannot connect to server.")

                if st.button("← Change Email", key="back_email"):
                    st.session_state.otp_step = False
                    st.rerun()

        # ---- Right panel: Hello banner ----
        with right_col:
            st.markdown("""
            <div class="auth-side">
                <h2>Hello, User!</h2>
                <p>If you don't have an account</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("SIGN UP", key="go_signup", use_container_width=True, type="secondary"):
                st.session_state.auth_mode = "signup"
                st.session_state.otp_step = False
                st.rerun()
