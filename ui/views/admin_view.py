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


from ui.theme import render_editorial_title, render_empty_state


def render():
    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")

    # Admin login gate
    if "admin_token" not in st.session_state or not st.session_state.admin_token:
        render_editorial_title(
            title="Curatorial Administration",
            subtitle="Restricted portal for faculty coordinators and system administrators.",
            meta_tag="PORTAL // ROOT ACCESS",
        )

        with st.form("admin_login_form"):
            admin_email = st.text_input("Administrator Identity", placeholder="admin@copilot.com")
            admin_password = st.text_input("Security Key", type="password", placeholder="••••••••")
            login_btn = st.form_submit_button("AUTHENTICATE PRIVILEGES →", type="primary", use_container_width=True)

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
                    st.success("✅ Privileges verified.")
                    st.rerun()
                else:
                    st.error(f"❌ {resp.json().get('detail', 'Access denied')}")
            except requests.ConnectionError:
                st.error("Cannot connect to the API server.")
            except Exception as e:
                st.error(f"Error: {str(e)}")
        return

    # === Admin Dashboard Header ===
    admin_token = st.session_state.admin_token
    headers = {"x-admin-token": admin_token}

    col_title, col_logout = st.columns([4, 1], gap="medium")
    with col_title:
        render_editorial_title(
            title="Curatorial Administration",
            subtitle="Management of institutional course materials, vector index dockets, and candidate assessments.",
            meta_tag="PORTAL // ACTIVE ROOT",
        )
    with col_logout:
        st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)
        if st.button("REVOKE ACCESS", key="admin_page_logout_btn", use_container_width=True, type="secondary"):
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
            "Upload textbooks, lecture notes, syllabus documents, and reference materials. "
            "You can select or drag-and-drop **multiple files at once**. "
            "These will be parsed, chunked, and embedded into **ChromaDB** (`admin_course_materials` collection) "
            "and made available to **all enrolled students** in Academic Q&A."
        )

        uploaded_files = st.file_uploader(
            "Choose documents (select one or multiple files)",
            type=["pdf", "docx", "pptx", "txt", "md"],
            help="Supported: PDF, DOCX, PPTX, TXT, MD. Hold Ctrl / Shift to select multiple files or drag and drop.",
            key="admin_files_uploader",
            accept_multiple_files=True,
        )

        doc_type = st.selectbox(
            "Material Type (applies to all selected files)",
            options=["textbook", "notes", "syllabus", "exam", "reference"],
            key="admin_doc_type",
        )

        if uploaded_files:
            total_size_kb = sum(f.size for f in uploaded_files) / 1024
            total_size_mb = total_size_kb / 1024
            size_str = f"{total_size_mb:.2f} MB" if total_size_mb >= 1.0 else f"{total_size_kb:.1f} KB"

            col_a, col_b = st.columns(2)
            col_a.metric("📁 Files Selected", f"{len(uploaded_files)} file(s)")
            col_b.metric("📐 Total Size", size_str)

            with st.expander(f"📋 Selected Files List ({len(uploaded_files)})", expanded=len(uploaded_files) <= 6):
                for i, f in enumerate(uploaded_files, 1):
                    f_kb = f.size / 1024
                    f_size_str = f"{f_kb / 1024:.2f} MB" if f_kb >= 1024 else f"{f_kb:.1f} KB"
                    st.markdown(f"**{i}.** `{f.name}` — *{f_size_str}*")

            btn_label = f"🚀 Upload & Index {len(uploaded_files)} Document{'s' if len(uploaded_files) > 1 else ''} into ChromaDB"
            if st.button(btn_label, type="primary", use_container_width=True, key="admin_upload_batch_btn"):
                total_count = len(uploaded_files)
                prog_bar = st.progress(0.0)
                status_box = st.empty()

                success_list = []
                error_list = []

                for idx, f in enumerate(uploaded_files):
                    status_box.info(f"⏳ Processing file {idx + 1} of {total_count}: **{f.name}**...")
                    try:
                        resp = requests.post(
                            f"{api_base}/api/v1/admin/upload-material",
                            files={"file": (f.name, f.getvalue())},
                            data={"doc_type": doc_type},
                            headers=headers,
                            timeout=180,
                        )
                        if resp.status_code == 200:
                            res_data = resp.json()
                            success_list.append(res_data)
                        else:
                            detail = resp.json().get("detail", "Upload failed") if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                            error_list.append({"filename": f.name, "error": detail})
                    except requests.ConnectionError:
                        error_list.append({"filename": f.name, "error": "Cannot connect to the API server."})
                    except Exception as e:
                        error_list.append({"filename": f.name, "error": str(e)})

                    prog_bar.progress((idx + 1) / total_count)

                status_box.empty()
                prog_bar.empty()

                total_chunks = sum(s.get("chunks_indexed", 0) for s in success_list)

                if success_list:
                    st.success(
                        f"✅ Successfully uploaded & indexed **{len(success_list)} of {total_count} file(s)**! "
                        f"Added **{total_chunks} chunks** to ChromaDB collection (`admin_course_materials`)."
                    )
                    with st.expander("📄 Indexed Documents Summary", expanded=True):
                        for s in success_list:
                            st.markdown(f"- ✅ **{s['filename']}** — `{s['chunks_indexed']} chunks` (ID: `{s['doc_id']}`)")

                if error_list:
                    st.error(f"❌ **{len(error_list)} file(s) failed:**")
                    for err in error_list:
                        st.markdown(f"- ⚠️ **{err['filename']}**: {err['error']}")

                if success_list:
                    st.info("💡 You can view all indexed documents and manage them in the **📋 View Materials** tab.")

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

