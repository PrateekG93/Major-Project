"""
Login / Signup View (Editorial Publication Aesthetic)
=====================================================
Asymmetric authentication gateway:
- Charcoal Ink Editorial Panel (Curriculum intelligence credentials & metadata)
- Bone Paper Form Area with High Typographic Contrast
- Strict Monospace OTP Inputs with Weighted Spring Transitions
"""

import requests
import streamlit as st


def render():
    st.markdown("""
    <style>
        header[data-testid="stHeader"] { visibility: hidden; }
        .block-container { padding-top: 2rem !important; max-width: 980px !important; }

        .auth-docket-wrapper {
            background: #FFFFFF;
            border: 1px solid #D8D1C5;
            border-radius: 6px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(20, 20, 19, 0.05);
            margin: 1.5rem auto 2rem auto;
            animation: editorialFadeIn 0.35s cubic-bezier(0.16, 1, 0.3, 1);
        }

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

        .auth-form-panel {
            background-color: #FFFFFF;
            padding: 2.5rem 2.5rem;
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

        .otp-input input {
            font-family: 'JetBrains Mono', monospace !important;
            font-size: 24px !important;
            letter-spacing: 12px !important;
            text-align: center !important;
            font-weight: 600 !important;
            color: #141413 !important;
            border: 2px solid #D8D1C5 !important;
            background-color: #F5F2EC !important;
            border-radius: 4px !important;
        }

        .otp-input input:focus {
            border-color: #D9381E !important;
            box-shadow: 0 0 0 3px rgba(217, 56, 30, 0.12) !important;
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
        col_side, col_form = st.columns([5, 6], gap="large")

        with col_side:
            st.markdown(
                """
                <div class="auth-editorial-panel" style="border-radius: 6px;">
                    <div>
                        <span class="editorial-tag" style="background: rgba(255,255,255,0.1); color: #F5F2EC;">REGISTRATION // NEW CANDIDATE</span>
                        <h2>Join the Academic Copilot Program</h2>
                        <p>
                            Create an institutional account to gain access to RAG-grounded syllabus tutoring,
                            resume skill-gap diagnostics, and timed technical viva simulations.
                        </p>
                    </div>
                    <div style="border-top: 1px solid rgba(255,255,255,0.12); padding-top: 1.2rem; margin-top: 2rem;">
                        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #8A8780; letter-spacing: 0.05em;">
                            INSTITUTION: IET JK LUXMIPAT UNIVERSITY<br>
                            SECURITY: SECURE HASHED PERSISTENCE
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_form:
            st.markdown('<div class="auth-header-label">Candidate Registration</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-sub-label">ENTER CREDENTIALS TO PROVISION PROFILE</div>', unsafe_allow_html=True)

            with st.form("signup_form"):
                name = st.text_input("Full Name", placeholder="e.g. Nakul Ranka", key="su_name")
                email = st.text_input("Institutional Email", placeholder="e.g. nakul@jklu.edu.in", key="su_email")
                password = st.text_input("Access Password", type="password", placeholder="••••••••", key="su_pass")
                signup_btn = st.form_submit_button("CREATE ACCOUNT →", type="primary", use_container_width=True)

            if signup_btn:
                if not name.strip():
                    st.error("Name is required.")
                elif not email or "@" not in email:
                    st.error("Enter a valid institutional email address.")
                elif len(password) < 4:
                    st.error("Password must be at least 4 characters.")
                else:
                    with st.spinner("Provisioning profile…"):
                        try:
                            resp = requests.post(
                                f"{api_base}/api/v1/auth/signup",
                                json={"name": name, "email": email, "password": password},
                                timeout=15,
                            )
                            if resp.status_code == 200:
                                st.success("✅ Profile provisioned successfully. Please authenticate.")
                                st.session_state.auth_mode = "signin"
                                st.session_state.otp_step = False
                                st.rerun()
                            else:
                                st.error(f"❌ {resp.json().get('detail', 'Signup failed')}")
                        except requests.ConnectionError:
                            st.error(
                                "❌ Backend service unreachable. Ensure FastAPI server is active at 127.0.0.1:8000."
                            )
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

            st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
            if st.button("ALREADY REGISTERED? SIGN IN", key="go_signin", use_container_width=True, type="secondary"):
                st.session_state.auth_mode = "signin"
                st.session_state.otp_step = False
                st.rerun()

    # ================================================================
    #  SIGN IN MODE
    # ================================================================
    else:
        col_side, col_form = st.columns([5, 6], gap="large")

        with col_side:
            st.markdown(
                """
                <div class="auth-editorial-panel" style="border-radius: 6px;">
                    <div>
                        <span class="editorial-tag" style="background: rgba(255,255,255,0.1); color: #F5F2EC;">VERIFICATION // DESK</span>
                        <h2>Welcome to Academic Copilot</h2>
                        <p>
                            An end-to-end preparation engine coupling dense semantic search with
                            supervised machine learning to pinpoint topic-level deficiencies and prescribe
                            curriculum remediation.
                        </p>
                    </div>
                    <div style="border-top: 1px solid rgba(255,255,255,0.12); padding-top: 1.2rem; margin-top: 2rem;">
                        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #8A8780; letter-spacing: 0.05em; line-height: 1.5;">
                            STATUS: ACTIVE DEPLOYMENT<br>
                            LLM PROVIDER: GROQ FAST INFERENCE<br>
                            ENGINE: MISTRAL / LLAMA 3.1
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_form:
            # -- Step 1: Email + Password --
            if not st.session_state.otp_step:
                st.markdown('<div class="auth-header-label">Sign In</div>', unsafe_allow_html=True)
                st.markdown('<div class="auth-sub-label">ENTER CREDENTIALS FOR ONE-TIME PASSCODE</div>', unsafe_allow_html=True)

                with st.form("signin_form"):
                    email = st.text_input("Email Address", placeholder="e.g. nakul@jklu.edu.in", key="si_email")
                    password = st.text_input("Password", type="password", placeholder="••••••••", key="si_pass")
                    signin_btn = st.form_submit_button("AUTHENTICATE →", type="primary", use_container_width=True)

                if signin_btn:
                    if not email or "@" not in email:
                        st.error("Enter a valid institutional email.")
                    elif not password:
                        st.error("Password cannot be blank.")
                    else:
                        with st.spinner("Validating credentials…"):
                            try:
                                resp = requests.post(
                                    f"{api_base}/api/v1/auth/signin",
                                    json={"email": email, "password": password},
                                    timeout=15,
                                )
                                if resp.status_code == 200:
                                    data = resp.json()
                                    if data.get("is_admin"):
                                        st.session_state.admin_token = data["admin_token"]
                                        st.session_state.admin_mode = True
                                        st.success("✅ Admin session authenticated.")
                                        st.rerun()
                                    else:
                                        st.session_state.signin_email = email.strip().lower()
                                        st.session_state.otp_step = True
                                        st.success(f"✅ {data.get('message', 'OTP dispatched.')}")
                                        st.rerun()
                                else:
                                    st.error(f"❌ {resp.json().get('detail', 'Authentication failed')}")
                            except requests.ConnectionError:
                                st.error("❌ Connection refused. Ensure FastAPI backend is active.")
                            except Exception as e:
                                st.error(f"Error: {str(e)}")

                st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                if st.button("NEW CANDIDATE? REGISTER HERE", key="go_signup", use_container_width=True, type="secondary"):
                    st.session_state.auth_mode = "signup"
                    st.session_state.otp_step = False
                    st.rerun()

            # -- Step 2: OTP verification --
            else:
                st.markdown('<div class="auth-header-label">Enter One-Time Passcode</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="auth-sub-label">PASSCODE DISPATCHED TO {st.session_state.signin_email}</div>',
                    unsafe_allow_html=True,
                )

                st.markdown(
                    """
                    <div style="background: var(--bg-paper); border: 1px solid var(--border-subtle); padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 1.2rem;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--ink-charcoal);">
                            NOTE: Check your email inbox or backend console (OTP_MODE=console).
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.form("otp_form"):
                    otp = st.text_input(
                        "6-Digit Code",
                        max_chars=6,
                        placeholder="000000",
                        key="otp_input",
                    )
                    col_a, col_b = st.columns([3, 2])
                    with col_a:
                        verify_btn = st.form_submit_button("VERIFY & ENTER →", type="primary", use_container_width=True)
                    with col_b:
                        resend_btn = st.form_submit_button("RESEND CODE", use_container_width=True)

                if verify_btn:
                    if not otp or len(otp) != 6:
                        st.error("Please enter the complete 6-digit passcode.")
                    else:
                        with st.spinner("Authorizing session…"):
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
                                    st.success("✅ Session verified. Welcome.")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {resp.json().get('detail', 'Verification code invalid')}")
                            except requests.ConnectionError:
                                st.error("❌ Connection failed.")
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
                            st.success("New passcode generated. Check your inbox or terminal console.")
                        else:
                            st.error("Failed to generate new passcode.")
                    except Exception:
                        st.error("Connection failed.")

                st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
                if st.button("← RETURN TO EMAIL ENTRY", key="back_email", type="secondary"):
                    st.session_state.otp_step = False
                    st.rerun()
