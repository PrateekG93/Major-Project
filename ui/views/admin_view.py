"""
Admin View
============
Admin portal for:
- Uploading course materials (textbooks, lecture notes)
- Viewing uploaded materials
- Viewing registered users
- Viewing MCQ interview results
Protected by admin email + password login.
"""

import time
from datetime import datetime

import requests
import streamlit as st


def render():
    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")

    # Admin login gate
    if "admin_token" not in st.session_state or not st.session_state.admin_token:
        st.markdown("# 🔐 Admin Portal")
        st.markdown("### Admin Authentication Required")
        st.caption("This portal is restricted to project administrators.")

        with st.form("admin_login_form"):
            admin_email = st.text_input("Admin Email", placeholder="admin@copilot.com")
            admin_password = st.text_input("Admin Password", type="password", placeholder="••••••••")
            login_btn = st.form_submit_button("🔑 Login as Admin", type="primary", use_container_width=True)

        if login_btn:
            try:
                resp = requests.post(
                    f"{api_base}/api/v1/admin/login",
                    json={"email": admin_email, "password": admin_password},
                    timeout=10,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    st.session_state.admin_token = result["admin_token"]
                    st.session_state.admin_mode = True
                    st.success("✅ Admin login successful!")
                    st.rerun()
                else:
                    st.error(f"❌ {resp.json().get('detail', 'Login failed')}")
            except requests.ConnectionError:
                st.error("Cannot connect to the API server.")
            except Exception as e:
                st.error(f"Error: {str(e)}")
        return

    # === Admin Dashboard Header ===
    admin_token = st.session_state.admin_token
    headers = {"x-admin-token": admin_token}

    col_title, col_logout = st.columns([4, 1])
    with col_title:
        st.markdown("# 🔐 Admin Portal")
        st.caption("System Administration • Course Materials • User Registry • MCQ Analytics")
    with col_logout:
        if st.button("🚪 Logout Admin", key="admin_page_logout_btn", use_container_width=True):
            st.session_state.admin_token = None
            st.session_state.admin_mode = False
            st.rerun()

    # --- Live System Summary Metrics ---
    try:
        mat_res = requests.get(f"{api_base}/api/v1/admin/materials", headers=headers, timeout=5)
        usr_res = requests.get(f"{api_base}/api/v1/admin/users", headers=headers, timeout=5)
        mcq_res = requests.get(f"{api_base}/api/v1/admin/results", headers=headers, timeout=5)

        mats = mat_res.json().get("materials", []) if mat_res.status_code == 200 else []
        usrs = usr_res.json().get("users", []) if usr_res.status_code == 200 else []
        mcqs = mcq_res.json().get("results", []) if mcq_res.status_code == 200 else []

        total_chunks = sum(m.get("chunks_indexed", 0) for m in mats)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📚 Materials", len(mats))
        c2.metric("🧩 Chunks in ChromaDB", total_chunks)
        c3.metric("👥 Registered Users", len(usrs))
        c4.metric("📊 MCQ Tests Taken", len(mcqs))
        st.markdown("---")
    except Exception:
        pass

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📚 Upload Materials", "📋 View Materials", "👥 Users", "📊 MCQ Results"
    ])

    # === Tab 1: Upload Course Materials ===
    with tab1:
        st.markdown("### 📚 Upload Course Materials")
        st.markdown(
            "Upload textbooks, lecture notes, and syllabus documents. "
            "These will be parsed, chunked, and embedded into **ChromaDB** (`admin_course_materials` collection) "
            "and made available to **all enrolled students** in Academic Q&A."
        )

        uploaded_file = st.file_uploader(
            "Choose a document",
            type=["pdf", "docx", "pptx", "txt", "md"],
            help="Supported: PDF, DOCX, PPTX, TXT, MD",
            key="admin_file_uploader",
        )

        doc_type = st.selectbox(
            "Material Type",
            options=["textbook", "notes", "syllabus", "exam", "reference"],
            key="admin_doc_type",
        )

        if uploaded_file:
            col_a, col_b = st.columns(2)
            col_a.metric("📁 File", uploaded_file.name)
            col_b.metric("📐 Size", f"{uploaded_file.size / 1024:.1f} KB")

            if st.button("🚀 Upload & Index into ChromaDB", type="primary", use_container_width=True, key="admin_upload_btn"):
                with st.spinner("Parsing document, generating embeddings, and indexing..."):
                    try:
                        resp = requests.post(
                            f"{api_base}/api/v1/admin/upload-material",
                            files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                            data={"doc_type": doc_type},
                            headers=headers,
                            timeout=120,
                        )
                        if resp.status_code == 200:
                            result = resp.json()
                            st.success(f"✅ Successfully uploaded! **{result['chunks_indexed']} chunks** indexed into ChromaDB.")
                            st.json(result)
                        else:
                            st.error(f"❌ {resp.json().get('detail', 'Upload failed')}")
                    except requests.ConnectionError:
                        st.error("Cannot connect to the API server.")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

    # === Tab 2: View Materials ===
    with tab2:
        col_m_head, col_m_ref = st.columns([4, 1])
        with col_m_head:
            st.markdown("### 📋 Uploaded Course Materials")
        with col_m_ref:
            if st.button("🔄 Refresh", key="refresh_materials", use_container_width=True):
                st.rerun()

        try:
            resp = requests.get(f"{api_base}/api/v1/admin/materials", headers=headers, timeout=10)
            if resp.status_code == 200:
                materials = resp.json().get("materials", [])
                if not materials:
                    st.info("No course materials uploaded yet. Upload your first textbook or lecture notes in Tab 1!")
                else:
                    st.caption(f"Showing {len(materials)} indexed materials in database:")
                    for mat in materials:
                        upload_time = datetime.fromtimestamp(mat["uploaded_at"]).strftime("%Y-%m-%d %H:%M")
                        with st.expander(f"📄 {mat['filename']}  |  {mat['chunks_indexed']} chunks  |  {upload_time}"):
                            c_info, c_btn = st.columns([4, 1])
                            with c_info:
                                st.markdown(f"- **Doc ID:** `{mat['doc_id']}`")
                                st.markdown(f"- **Category:** `{mat['doc_type']}`")
                                st.markdown(f"- **Chunks in Vector DB:** `{mat['chunks_indexed']}`")
                                st.markdown(f"- **Uploaded At:** {upload_time}")
                            with c_btn:
                                if st.button("🗑️ Delete", key=f"del_{mat['doc_id']}", use_container_width=True):
                                    try:
                                        del_resp = requests.delete(
                                            f"{api_base}/api/v1/admin/materials/{mat['doc_id']}",
                                            headers=headers, timeout=10,
                                        )
                                        if del_resp.status_code == 200:
                                            st.success("Deleted material successfully.")
                                            st.rerun()
                                        else:
                                            st.error("Delete failed.")
                                    except Exception as e:
                                        st.error(f"Error deleting: {e}")
            else:
                st.error("Failed to fetch materials from backend.")
        except requests.ConnectionError:
            st.warning("API server not connected.")
        except Exception as e:
            st.error(f"Error: {str(e)}")

    # === Tab 3: Users ===
    with tab3:
        col_u_head, col_u_ref = st.columns([4, 1])
        with col_u_head:
            st.markdown("### 👥 Registered Users (SQLite)")
        with col_u_ref:
            if st.button("🔄 Refresh", key="refresh_users", use_container_width=True):
                st.rerun()

        try:
            resp = requests.get(f"{api_base}/api/v1/admin/users", headers=headers, timeout=10)
            if resp.status_code == 200:
                users = resp.json().get("users", [])
                if not users:
                    st.info("No users registered yet.")
                else:
                    st.markdown(f"**Total Registered Users:** `{len(users)}`")
                    for user in users:
                        created = datetime.fromtimestamp(user["created_at"]).strftime("%Y-%m-%d %H:%M")
                        last_login = datetime.fromtimestamp(user["last_login"]).strftime("%Y-%m-%d %H:%M") if user.get("last_login") else "Never"
                        name_display = f" ({user['name']})" if user.get("name") else ""
                        with st.container():
                            st.markdown(
                                f"👤 **{user['email']}**{name_display}  \n"
                                f"&nbsp;&nbsp;&nbsp;&nbsp;📅 **Joined:** {created} &nbsp;|&nbsp; 🕒 **Last Login:** {last_login}"
                            )
                            st.divider()
            else:
                st.error("Failed to fetch users.")
        except requests.ConnectionError:
            st.warning("API server not connected.")
        except Exception as e:
            st.error(f"Error: {str(e)}")

    # === Tab 4: MCQ Results ===
    with tab4:
        col_r_head, col_r_ref = st.columns([4, 1])
        with col_r_head:
            st.markdown("### 📊 All MCQ Interview Results (SQLite)")
        with col_r_ref:
            if st.button("🔄 Refresh", key="refresh_mcq_results", use_container_width=True):
                st.rerun()

        try:
            resp = requests.get(f"{api_base}/api/v1/admin/results", headers=headers, timeout=10)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if not results:
                    st.info("No MCQ interviews completed yet.")
                else:
                    st.markdown(f"**Total Interview Sessions:** `{len(results)}`")
                    for r in results:
                        created = datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d %H:%M")
                        score = f"{r['total_correct']} / {r['total_answered']}" if r["total_answered"] > 0 else "N/A"
                        status = "✅ Complete" if r["is_complete"] else "⏳ In Progress"
                        with st.expander(f"🎯 {r['email']} — Score: {score} ({status}) — {created}"):
                            st.markdown(f"- **Session ID:** `{r['session_id']}`")
                            st.markdown(f"- **Student Email:** `{r['email']}`")
                            st.markdown(f"- **Questions Answered:** `{r['total_answered']} / {r['num_questions']}`")
                            st.markdown(f"- **Total Correct:** `{r['total_correct']}`")
                            st.markdown(f"- **Session Status:** {status}")
                            st.markdown(f"- **Started At:** {created}")
            else:
                st.error("Failed to fetch results.")
        except Exception as e:
            st.error(f"Error: {str(e)}")

