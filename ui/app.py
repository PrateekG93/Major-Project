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

# Page config must be the first Streamlit command
st.set_page_config(
    page_title="Academic & Career Copilot",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for premium styling
st.markdown("""
<style>
    /* Global styles */
    .main .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    }
    [data-testid="stSidebar"] .stMarkdown h1,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3,
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown li {
        color: #e0e0e0;
    }

    /* Card-like containers */
    .stExpander {
        border: 1px solid #e0e0e0;
        border-radius: 10px;
    }

    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85em;
        font-weight: 600;
    }
    .badge-success { background-color: #d4edda; color: #155724; }
    .badge-warning { background-color: #fff3cd; color: #856404; }
    .badge-danger { background-color: #f8d7da; color: #721c24; }
    .badge-info { background-color: #d1ecf1; color: #0c5460; }

    /* Metric cards */
    [data-testid="stMetric"] {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 10px;
        padding: 15px;
    }
</style>
""", unsafe_allow_html=True)

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
#  Sidebar
# -------------------------------------------------------------------
with st.sidebar:
    st.markdown("# 🎓 Academic Copilot")
    st.markdown("---")

    if is_admin:
        # ---------- Admin sidebar ----------
        st.markdown("### 🛡️ Admin Portal")
        st.caption("Managing course materials, users & MCQ data.")
        if st.button("🚪 Admin Logout", key="admin_logout_btn", use_container_width=True):
            st.session_state.admin_mode = False
            st.session_state.admin_token = None
            st.rerun()

    elif is_student:
        # ---------- Student sidebar ----------
        st.markdown(f"👤 **{st.session_state.user_email}**")
        if st.button("🚪 Logout", key="student_logout_btn", use_container_width=True):
            st.session_state.session_token = None
            st.session_state.user_email = None
            st.session_state.otp_step = False
            st.session_state.auth_mode = "signin"
            st.rerun()

        st.markdown("---")

        # Student Navigation buttons
        pages = {
            "upload": ("📄", "Upload Documents"),
            "chat": ("💬", "Academic Q&A"),
            "interview": ("🎯", "Mock Interview"),
            "dashboard": ("📊", "Performance Dashboard"),
        }

        for page_key, (icon, label) in pages.items():
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{page_key}",
                use_container_width=True,
                type="primary" if st.session_state.current_page == page_key else "secondary",
            ):
                st.session_state.current_page = page_key
                st.rerun()

    else:
        # ---------- Logged-out sidebar ----------
        st.info("👋 Sign in or create an account to get started.")

    # Common footer
    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    st.session_state.api_base_url = st.text_input(
        "API Server URL",
        value=st.session_state.api_base_url,
        help="FastAPI backend URL (default: http://127.0.0.1:8000)",
    )

    st.markdown("---")
    st.markdown(
        "<p style='text-align:center; color:#888; font-size:0.8em;'>"
        "Built by Nakul, Prateek & Siddharth<br>"
        "JKLU • Major Project PR1107"
        "</p>",
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
