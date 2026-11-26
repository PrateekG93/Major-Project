"""
Login / Signup / Verification / Password Recovery View
=======================================================
Editorial publication authentication gateway supporting:
- Registration with password confirmation & strength validation
- Email OTP verification screen (for signup & login) with 60s countdown & resend
- Forgot Password -> Reset OTP -> New Password creation flow
- Admin portal authentication
"""

import time
import requests
import streamlit as st
import streamlit.components.v1 as components


def _render_cooldown_timer(cooldown_until: float):
    """Render a client-side live countdown timer for OTP resend cooldown."""
    remaining = max(0, int(cooldown_until - time.time()))
    if remaining <= 0:
        return
    components.html(
        f"""
        <div id="otp-cd" style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #5A5852; padding: 4px 0;">
            Resend available in <strong id="cd-sec" style="color: #D9381E;">{remaining}</strong>s
        </div>
        <script>
            (function() {{
                let sec = {remaining};
                const el = document.getElementById('cd-sec');
                const box = document.getElementById('otp-cd');
                const timer = setInterval(() => {{
                    sec -= 1;
                    if (sec <= 0) {{
                        clearInterval(timer);
                        if (box) box.innerHTML = '<span style="color:#2D5A27;">You can now request a new OTP code.</span>';
                    }} else if (el) {{
                        el.textContent = sec;
                    }}
                }}, 1000);
            }})();
        </script>
        """,
        height=30,
    )


def render():
    st.markdown("""
    <style>
        header[data-testid="stHeader"] { visibility: hidden; }
        .block-container { padding-top: 2rem !important; max-width: 980px !important; }

        .auth-editorial-panel {
            background-color: #141413;
            color: #F5F2EC;
            padding: 3rem 2.2rem;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            border-right: 1px solid #2A2A28;
        }

        .auth-editorial-panel h2 {
            font-family: 'Instrument Serif', Georgia, serif !important;
            font-size: 2.35rem !important;
            color: #F5F2EC !important;
            line-height: 1.15 !important;
            margin: 1rem 0 0.8rem 0 !important;
            font-weight: 400 !important;
        }

        .auth-editorial-panel p {
            color: #A8A49C !important;
            font-size: 0.92rem !important;
            line-height: 1.65 !important;
        }

        .auth-header-label {
            font-family: 'Instrument Serif', Georgia, serif;
            font-size: 2.1rem;
            color: #141413;
            margin-bottom: 0.3rem;
            font-weight: 400;
        }

        .auth-sub-label {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            color: #8A8780;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 1.5rem;
        }
    </style>
    """, unsafe_allow_html=True)

    # -------- Session-state defaults --------
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "signin"  # 'signin' | 'signup' | 'forgot'
    if "otp_step" not in st.session_state:
        st.session_state.otp_step = False
    if "otp_purpose" not in st.session_state:
        st.session_state.otp_purpose = "login"  # 'signup' | 'login'
    if "signin_email" not in st.session_state:
        st.session_state.signin_email = ""
    if "otp_cooldown_until" not in st.session_state:
        st.session_state.otp_cooldown_until = 0.0
    if "forgot_step" not in st.session_state:
        st.session_state.forgot_step = "email"  # 'email' | 'otp' | 'new_password'
    if "forgot_email" not in st.session_state:
        st.session_state.forgot_email = ""
    if "forgot_otp_verified" not in st.session_state:
        st.session_state.forgot_otp_verified = ""

    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")

    col_side, col_form = st.columns([5, 6], gap="large")

    # ================================================================
    #  LEFT EDITORIAL PANEL
    # ================================================================
    with col_side:
        if st.session_state.auth_mode == "signup":
            panel_tag = "REGISTRATION // NEW CANDIDATE"
            panel_title = "Join the Academic Copilot Program"
            panel_desc = (
                "Create a verified account to access RAG-grounded syllabus tutoring, "
                "curated topic question banks, and adaptive AI audio interviews."
            )
        elif st.session_state.auth_mode == "forgot":
            panel_tag = "SECURITY // RECOVERY DESK"
            panel_title = "Recover Account Access"
            panel_desc = (
                "Verify your registered email address with a one-time passcode to "
                "securely reset your password and revoke prior active sessions."
            )
        else:
            panel_tag = "VERIFICATION // DESK"
            panel_title = "Welcome to Academic Copilot"
            panel_desc = (
                "An end-to-end preparation engine coupling hybrid RAG retrieval, "
                "topic-structured question banks, and adaptive AI audio interviews."
            )

        st.markdown(
            f"""
            <div class="auth-editorial-panel" style="border-radius: 6px;">
                <div>
                    <span class="editorial-tag" style="background: rgba(255,255,255,0.1); color: #F5F2EC;">{panel_tag}</span>
                    <h2>{panel_title}</h2>
                    <p>{panel_desc}</p>
                </div>
                <div style="border-top: 1px solid rgba(255,255,255,0.12); padding-top: 1.2rem; margin-top: 2rem;">
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #8A8780; letter-spacing: 0.05em; line-height: 1.5;">
                        INSTITUTION: IET JKLU // PR1107<br>
                        SECURITY: BCRYPT + HMAC-SHA256 OTP<br>
                        AI ENGINE: GROQ WHISPER + LLAMA / RAG
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ================================================================
    #  RIGHT FORM PANEL
    # ================================================================
    with col_form:
        # ------------------------------------------------------------
        #  CASE A: OTP VERIFICATION SCREEN (SIGNUP OR LOGIN)
        # ------------------------------------------------------------
        if st.session_state.otp_step:
            purpose = st.session_state.otp_purpose
            title_txt = "Verify Your Email" if purpose == "signup" else "Enter One-Time Passcode"
            sub_txt = (
                f"ACTIVATION CODE DISPATCHED TO {st.session_state.signin_email}"
                if purpose == "signup"
                else f"LOGIN PASSCODE DISPATCHED TO {st.session_state.signin_email}"
            )
            st.markdown(f'<div class="auth-header-label">{title_txt}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="auth-sub-label">{sub_txt}</div>', unsafe_allow_html=True)

            st.markdown(
                """
                <div style="background: var(--bg-paper); border: 1px solid var(--border-subtle); padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 1rem;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--ink-charcoal);">
                        NOTE: Enter the 6-digit OTP (valid for 5 minutes). Check your email inbox or backend terminal if OTP_MODE=console.
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            _render_cooldown_timer(st.session_state.otp_cooldown_until)

            with st.form("otp_form"):
                otp = st.text_input(
                    "6-Digit Verification Code",
                    max_chars=6,
                    placeholder="000000",
                    key="otp_input",
                )
                verify_btn = st.form_submit_button("VERIFY & CONTINUE →", type="primary", use_container_width=True)

            if verify_btn:
                if not otp or len(otp.strip()) != 6 or not otp.strip().isdigit():
                    st.error("Please enter the complete 6-digit numeric passcode.")
                else:
                    endpoint = "/api/v1/auth/verify-signup" if purpose == "signup" else "/api/v1/auth/verify-otp"
                    with st.spinner("Verifying passcode…"):
                        try:
                            resp = requests.post(
                                f"{api_base}{endpoint}",
                                json={"email": st.session_state.signin_email, "otp": otp.strip(), "purpose": purpose},
                                timeout=15,
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                st.session_state.session_token = data["session_token"]
                                st.session_state.user_email = data["email"]
                                st.session_state.otp_step = False
                                st.session_state.auth_mode = "signin"
                                st.success("✅ Verification successful. Welcome!")
                                st.rerun()
                            else:
                                st.error(f"❌ {resp.json().get('detail', 'Verification failed')}")
                        except requests.ConnectionError:
                            st.error("❌ Backend service unreachable.")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

            col_r1, col_r2 = st.columns(2, gap="small")
            with col_r1:
                if st.button("RESEND OTP CODE", key="resend_otp_btn", use_container_width=True, type="secondary"):
                    with st.spinner("Requesting new code…"):
                        try:
                            r_resp = requests.post(
                                f"{api_base}/api/v1/auth/request-otp",
                                json={"email": st.session_state.signin_email, "purpose": purpose},
                                timeout=15,
                            )
                            if r_resp.status_code == 200:
                                rdata = r_resp.json()
                                cd = rdata.get("cooldown_seconds", 60)
                                st.session_state.otp_cooldown_until = time.time() + cd
                                st.success(f"✅ {rdata.get('message', 'New passcode generated.')}")
                                st.rerun()
                            else:
                                st.error(f"❌ {r_resp.json().get('detail', 'Could not resend OTP.')}")
                        except Exception as e:
                            st.error(f"Connection failed: {e}")
            with col_r2:
                if st.button("← BACK TO SIGN IN", key="back_email", use_container_width=True, type="secondary"):
                    st.session_state.otp_step = False
                    st.session_state.auth_mode = "signin"
                    st.rerun()
            return

        # ------------------------------------------------------------
        #  CASE B: SIGN UP MODE
        # ------------------------------------------------------------
        if st.session_state.auth_mode == "signup":
            st.markdown('<div class="auth-header-label">Candidate Registration</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-sub-label">CREATE ACCOUNT & VERIFY EMAIL VIA OTP</div>', unsafe_allow_html=True)

            with st.form("signup_form"):
                name = st.text_input("Full Name", placeholder="e.g. Nakul Ranka", key="su_name")
                email = st.text_input("Institutional Email", placeholder="e.g. nakul@jklu.edu.in", key="su_email")
                password = st.text_input(
                    "Password (min 8 chars, letters + numbers)",
                    type="password",
                    placeholder="••••••••",
                    key="su_pass",
                )
                confirm_pw = st.text_input(
                    "Confirm Password",
                    type="password",
                    placeholder="••••••••",
                    key="su_confirm_pass",
                )
                signup_btn = st.form_submit_button("CREATE ACCOUNT & SEND OTP →", type="primary", use_container_width=True)

            if signup_btn:
                if not name.strip():
                    st.error("Full name is required.")
                elif not email or "@" not in email:
                    st.error("Enter a valid email address.")
                elif len(password) < 8:
                    st.error("Password must be at least 8 characters long.")
                elif password != confirm_pw:
                    st.error("Passwords do not match.")
                else:
                    with st.spinner("Creating profile and sending verification OTP…"):
                        try:
                            resp = requests.post(
                                f"{api_base}/api/v1/auth/signup",
                                json={
                                    "name": name.strip(),
                                    "email": email.strip(),
                                    "password": password,
                                    "confirm_password": confirm_pw,
                                },
                                timeout=20,
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                st.session_state.signin_email = email.strip().lower()
                                st.session_state.otp_purpose = "signup"
                                st.session_state.otp_step = True
                                st.session_state.otp_cooldown_until = time.time() + data.get("cooldown_seconds", 60)
                                st.success(f"✅ {data.get('message', 'Verification code sent.')}")
                                st.rerun()
                            else:
                                st.error(f"❌ {resp.json().get('detail', 'Signup failed')}")
                        except requests.ConnectionError:
                            st.error("❌ Backend service unreachable at 127.0.0.1:8000.")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

            st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)
            if st.button("ALREADY REGISTERED? SIGN IN", key="go_signin", use_container_width=True, type="secondary"):
                st.session_state.auth_mode = "signin"
                st.session_state.otp_step = False
                st.rerun()
            return

        # ------------------------------------------------------------
        #  CASE C: FORGOT PASSWORD / RESET FLOW
        # ------------------------------------------------------------
        if st.session_state.auth_mode == "forgot":
            st.markdown('<div class="auth-header-label">Reset Password</div>', unsafe_allow_html=True)

            if st.session_state.forgot_step == "email":
                st.markdown('<div class="auth-sub-label">STEP 1 // ENTER REGISTERED EMAIL</div>', unsafe_allow_html=True)
                with st.form("forgot_email_form"):
                    f_email = st.text_input("Registered Email Address", placeholder="e.g. nakul@jklu.edu.in", key="fp_email")
                    send_reset_btn = st.form_submit_button("SEND RECOVERY OTP →", type="primary", use_container_width=True)

                if send_reset_btn:
                    if not f_email or "@" not in f_email:
                        st.error("Please enter a valid email address.")
                    else:
                        with st.spinner("Sending recovery code…"):
                            try:
                                resp = requests.post(
                                    f"{api_base}/api/v1/auth/forgot-password",
                                    json={"email": f_email.strip()},
                                    timeout=20,
                                )
                                if resp.status_code == 200:
                                    data = resp.json()
                                    st.session_state.forgot_email = f_email.strip().lower()
                                    st.session_state.forgot_step = "otp"
                                    st.session_state.otp_cooldown_until = time.time() + data.get("cooldown_seconds", 60)
                                    st.success(f"✅ {data.get('message')}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {resp.json().get('detail', 'Request failed')}")
                            except Exception as e:
                                st.error(f"Error: {str(e)}")

            elif st.session_state.forgot_step == "otp":
                st.markdown(f'<div class="auth-sub-label">STEP 2 // VERIFY RECOVERY OTP ({st.session_state.forgot_email})</div>', unsafe_allow_html=True)
                _render_cooldown_timer(st.session_state.otp_cooldown_until)

                with st.form("forgot_otp_form"):
                    f_otp = st.text_input("6-Digit Reset OTP", max_chars=6, placeholder="000000", key="fp_otp")
                    verify_reset_btn = st.form_submit_button("VERIFY RECOVERY OTP →", type="primary", use_container_width=True)

                if verify_reset_btn:
                    if not f_otp or len(f_otp.strip()) != 6 or not f_otp.strip().isdigit():
                        st.error("Enter the 6-digit numeric OTP.")
                    else:
                        try:
                            resp = requests.post(
                                f"{api_base}/api/v1/auth/verify-reset-otp",
                                json={"email": st.session_state.forgot_email, "otp": f_otp.strip(), "purpose": "password_reset"},
                                timeout=15,
                            )
                            if resp.status_code == 200:
                                st.session_state.forgot_otp_verified = f_otp.strip()
                                st.session_state.forgot_step = "new_password"
                                st.rerun()
                            else:
                                st.error(f"❌ {resp.json().get('detail', 'Invalid OTP')}")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

                if st.button("RESEND RECOVERY OTP", key="resend_fp_otp", use_container_width=True, type="secondary"):
                    try:
                        r = requests.post(
                            f"{api_base}/api/v1/auth/request-otp",
                            json={"email": st.session_state.forgot_email, "purpose": "password_reset"},
                            timeout=15,
                        )
                        if r.status_code == 200:
                            st.session_state.otp_cooldown_until = time.time() + r.json().get("cooldown_seconds", 60)
                            st.success(f"✅ {r.json().get('message')}")
                            st.rerun()
                        else:
                            st.error(f"❌ {r.json().get('detail', 'Cooldown active.')}")
                    except Exception as e:
                        st.error(f"Error: {e}")

            elif st.session_state.forgot_step == "new_password":
                st.markdown('<div class="auth-sub-label">STEP 3 // CREATE NEW PASSWORD</div>', unsafe_allow_html=True)
                with st.form("reset_pw_form"):
                    new_pw = st.text_input("New Password (min 8 chars, letters + numbers)", type="password", key="fp_new_pw")
                    confirm_new_pw = st.text_input("Confirm New Password", type="password", key="fp_conf_pw")
                    reset_submit = st.form_submit_button("UPDATE PASSWORD →", type="primary", use_container_width=True)

                if reset_submit:
                    if len(new_pw) < 8:
                        st.error("Password must be at least 8 characters long.")
                    elif new_pw != confirm_new_pw:
                        st.error("Passwords do not match.")
                    else:
                        try:
                            resp = requests.post(
                                f"{api_base}/api/v1/auth/reset-password",
                                json={
                                    "email": st.session_state.forgot_email,
                                    "otp": st.session_state.forgot_otp_verified,
                                    "new_password": new_pw,
                                    "confirm_password": confirm_new_pw,
                                },
                                timeout=15,
                            )
                            if resp.status_code == 200:
                                st.success("✅ Password reset successfully! Please sign in with your new password.")
                                st.session_state.auth_mode = "signin"
                                st.session_state.forgot_step = "email"
                                st.session_state.forgot_otp_verified = ""
                                st.rerun()
                            else:
                                st.error(f"❌ {resp.json().get('detail', 'Password reset failed')}")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

            st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)
            if st.button("← RETURN TO SIGN IN", key="fp_back_signin", use_container_width=True, type="secondary"):
                st.session_state.auth_mode = "signin"
                st.session_state.forgot_step = "email"
                st.rerun()
            return

        # ------------------------------------------------------------
        #  CASE D: SIGN IN MODE
        # ------------------------------------------------------------
        st.markdown('<div class="auth-header-label">Sign In</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-sub-label">ENTER CREDENTIALS FOR VERIFIED ACCESS</div>', unsafe_allow_html=True)

        with st.form("signin_form"):
            email = st.text_input("Email Address", placeholder="e.g. nakul@jklu.edu.in", key="si_email")
            password = st.text_input("Password", type="password", placeholder="••••••••", key="si_pass")
            signin_btn = st.form_submit_button("AUTHENTICATE →", type="primary", use_container_width=True)

        if signin_btn:
            if not email or "@" not in email:
                st.error("Enter a valid email address.")
            elif not password:
                st.error("Password cannot be blank.")
            else:
                with st.spinner("Validating credentials…"):
                    try:
                        resp = requests.post(
                            f"{api_base}/api/v1/auth/signin",
                            json={"email": email.strip(), "password": password},
                            timeout=20,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("is_admin"):
                                st.session_state.admin_token = data["admin_token"]
                                st.session_state.admin_mode = True
                                st.success("✅ Admin session authenticated.")
                                st.rerun()
                            elif data.get("session_token"):
                                st.session_state.session_token = data["session_token"]
                                st.session_state.user_email = data["email"]
                                st.success("✅ Signed in successfully.")
                                st.rerun()
                            else:
                                st.session_state.signin_email = email.strip().lower()
                                st.session_state.otp_purpose = "login"
                                st.session_state.otp_step = True
                                st.session_state.otp_cooldown_until = time.time() + data.get("cooldown_seconds", 60)
                                st.success(f"✅ {data.get('message', 'OTP dispatched.')}")
                                st.rerun()
                        elif resp.status_code == 403 and resp.headers.get("X-Requires-Verification") == "true":
                            st.session_state.signin_email = email.strip().lower()
                            st.session_state.otp_purpose = "signup"
                            st.session_state.otp_step = True
                            st.session_state.otp_cooldown_until = time.time() + 60
                            st.warning(f"⚠️ {resp.json().get('detail', 'Please verify your email.')}")
                            st.rerun()
                        else:
                            st.error(f"❌ {resp.json().get('detail', 'Authentication failed')}")
                    except requests.ConnectionError:
                        st.error("❌ Connection refused. Ensure FastAPI backend is active at 127.0.0.1:8000.")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

        col_act1, col_act2 = st.columns(2, gap="small")
        with col_act1:
            if st.button("NEW CANDIDATE? REGISTER", key="go_signup", use_container_width=True, type="secondary"):
                st.session_state.auth_mode = "signup"
                st.session_state.otp_step = False
                st.rerun()
        with col_act2:
            if st.button("FORGOT PASSWORD?", key="go_forgot", use_container_width=True, type="secondary"):
                st.session_state.auth_mode = "forgot"
                st.session_state.forgot_step = "email"
                st.rerun()
