"""
Streamlit Application Entry Point
====================================
Multi-page navigation with sidebar across views:
- Login / Signup (first screen, unauthenticated)
- Upload Documents
- Academic Q&A Chat
- Mock Interview
- Performance Dashboard
- Admin Portal (via admin credentials on login screen)
"""

import streamlit as st
from ui.theme import apply_theme

# Page config must be the first Streamlit command
st.set_page_config(
    page_title="Academic & Career Copilot",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply global editorial theme & typography
apply_theme()

# Initialize session state
if "session_token" not in st.session_state:
    st.session_state.session_token = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "current_page" not in st.session_state:
    st.session_state.current_page = "upload"
if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = "http://127.0.0.1:8000"
if "admin_mode" not in st.session_state:
    st.session_state.admin_mode = False
if "admin_token" not in st.session_state:
    st.session_state.admin_token = None


# -------------------------------------------------------------------
#  Determine current auth status
# -------------------------------------------------------------------
is_admin = st.session_state.admin_mode and st.session_state.admin_token
is_student = bool(st.session_state.session_token) and not is_admin
is_logged_out = not is_admin and not is_student

# -------------------------------------------------------------------
#  Sidebar (Editorial Masthead & Precision Navigation)
# -------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div style="padding-bottom: 0.8rem; border-bottom: 1px solid var(--border-subtle); margin-bottom: 1rem;">
            <div style="font-family: var(--font-mono); font-size: 0.68rem; letter-spacing: 0.1em; color: var(--accent-red); text-transform: uppercase;">
                PR1107 // EDITION 2026
            </div>
            <div style="font-family: var(--font-serif); font-size: 1.85rem; color: var(--ink-charcoal); line-height: 1.1; margin: 0.2rem 0;">
                Academic Copilot
            </div>
            <div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">
                RAG + Supervised Intelligence
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if is_admin:
        # ---------- Admin sidebar ----------
        st.markdown(
            """
            <div style="margin-bottom: 0.8rem;">
                <span class="editorial-tag">ACCESS // ROOT ADMIN</span>
                <div style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--ink-muted); margin-top: 4px;">
                    Curatorial Management
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🚪 Log Out Admin", key="admin_logout_btn", use_container_width=True):
            st.session_state.admin_mode = False
            st.session_state.admin_token = None
            st.rerun()

    elif is_student:
        # ---------- Student sidebar ----------
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.75rem 0.9rem; border-radius: 4px; margin-bottom: 1rem;">
                <div style="font-family: var(--font-mono); font-size: 0.65rem; color: var(--ink-tertiary); text-transform: uppercase; letter-spacing: 0.08em;">
                    AUTHENTICATED CANDIDATE
                </div>
                <div style="font-family: var(--font-sans); font-size: 0.86rem; font-weight: 600; color: var(--ink-charcoal); margin-top: 2px; word-break: break-all;">
                    {st.session_state.user_email}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """<div style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-tertiary); letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0.5rem;">
                SECTIONS
            </div>""",
            unsafe_allow_html=True,
        )

        # Student Navigation buttons
        pages = {
            "upload": ("01", "Upload Dossier"),
            "chat": ("02", "Curriculum Q&A"),
            "interview": ("03", "Mock Interview"),
            "dashboard": ("04", "Diagnostics"),
        }

        for page_key, (num, label) in pages.items():
            is_active = st.session_state.current_page == page_key
            if st.button(
                f"{num} — {label}",
                key=f"nav_{page_key}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.current_page = page_key
                st.rerun()

        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        if st.button("Log Out", key="student_logout_btn", use_container_width=True):
            st.session_state.session_token = None
            st.session_state.user_email = None
            st.session_state.otp_step = False
            st.session_state.auth_mode = "signin"
            st.rerun()

    else:
        # ---------- Logged-out sidebar ----------
        st.markdown(
            """
            <div style="background: var(--bg-card); border: 1px dashed var(--border-subtle); padding: 0.9rem; border-radius: 4px; margin-bottom: 1rem;">
                <div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--accent-red); font-weight: 600; letter-spacing: 0.06em;">
                    GATEWAY // UNVERIFIED
                </div>
                <div style="font-family: var(--font-sans); font-size: 0.85rem; color: var(--ink-muted); margin-top: 4px;">
                    Authenticate to access curricular RAG and timed mock interviews.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Common footer
    st.markdown("---")
    with st.expander("SERVER CONFIG", expanded=False):
        st.session_state.api_base_url = st.text_input(
            "API URL",
            value=st.session_state.api_base_url,
            help="FastAPI backend host address",
        )

    st.markdown(
        """
        <div style="padding-top: 0.5rem; border-top: 1px solid var(--border-subtle); text-align: left;">
            <div style="font-family: var(--font-mono); font-size: 0.65rem; color: var(--ink-tertiary); letter-spacing: 0.06em; line-height: 1.5;">
                PROJECT // PR1107<br>
                JKLU IET • JAIPUR<br>
                NAKUL • PRATEEK • SIDDHARTH
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -------------------------------------------------------------------
#  Page Router
# -------------------------------------------------------------------
if is_admin:
    from ui.views.admin_view import render
    render()
elif is_logged_out:
    from ui.views.login_view import render
    render()
else:
    # Authenticated student pages
    if st.session_state.current_page == "upload":
        from ui.views.upload_view import render
        render()
    elif st.session_state.current_page == "chat":
        from ui.views.chat_view import render
        render()
    elif st.session_state.current_page == "interview":
        from ui.views.interview_view import render
        render()
    elif st.session_state.current_page == "dashboard":
        from ui.views.dashboard_view import render
        render()
