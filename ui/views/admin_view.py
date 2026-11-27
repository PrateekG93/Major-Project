"""
Admin View
============
Admin portal for:
- Uploading course materials (textbooks, lecture notes)
- Viewing uploaded materials
- Viewing registered users (verification & dossier status)
- Viewing Adaptive AI Audio Interview & Timed MCQ Battery results
- Managing the 11-topic Centralized Question Bank
- Inspecting & verifying Email OTP / SMTP configuration
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
        aud_res = requests.get(f"{api_base}/api/v1/admin/audio-results", headers=headers, timeout=5)

        mats = mat_res.json().get("materials", []) if mat_res.status_code == 200 else []
        usrs = usr_res.json().get("users", []) if usr_res.status_code == 200 else []
        mcqs = mcq_res.json().get("results", []) if mcq_res.status_code == 200 else []
        auds = aud_res.json().get("results", []) if aud_res.status_code == 200 else []

        total_chunks = sum(m.get("chunks_indexed", 0) for m in mats)
        verified_cnt = sum(1 for u in usrs if u.get("is_verified"))

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("📚 Materials", len(mats))
        c2.metric("🧩 Chunks", total_chunks, help="Total indexed chunks in ChromaDB")
        c3.metric("👥 Users", f"{len(usrs)} ({verified_cnt}✓)", help="Registered users (email-verified count)")
        c4.metric("🎙️ Audio", len(auds), help="Adaptive AI Audio Interview sessions")
        c5.metric("📊 MCQs", len(mcqs), help="Timed MCQ Examination Battery sessions")
        st.markdown("---")
    except Exception:
        pass

    # Tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📚 Upload Materials",
        "📋 View Materials",
        "👥 Users",
        "📊 Assessment Results",
        "🌐 Question Bank",
        "🔐 Auth & OTP Config",
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
                                st.markdown(f"- **Document Type:** `{mat['doc_type']}`")
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
                        ver_badge = "✅ Verified" if user.get("is_verified") else "⏳ Unverified"
                        dossier_bits = []
                        if user.get("has_resume"):
                            dossier_bits.append("Resume")
                        if user.get("has_jd"):
                            role_lbl = user.get("jd_role") or "JD"
                            comp_lbl = f" @ {user['jd_company']}" if user.get("jd_company") else ""
                            dossier_bits.append(f"JD: {role_lbl}{comp_lbl}")
                        dossier_str = " | ".join(dossier_bits) if dossier_bits else "None uploaded"
                        with st.container():
                            st.markdown(
                                f"👤 **{user['email']}**{name_display} — `{ver_badge}`  \n"
                                f"&nbsp;&nbsp;&nbsp;&nbsp;📅 **Joined:** {created} &nbsp;|&nbsp; 🕒 **Last Login:** {last_login} &nbsp;|&nbsp; 📄 **Dossier:** {dossier_str}"
                            )
                            st.divider()
            else:
                st.error("Failed to fetch users.")
        except requests.ConnectionError:
            st.warning("API server not connected.")
        except Exception as e:
            st.error(f"Error: {str(e)}")

    # === Tab 4: Assessment Results (Audio Interviews + MCQ Batteries) ===
    with tab4:
        col_r_head, col_r_ref = st.columns([4, 1])
        with col_r_head:
            st.markdown("### 📊 Assessment Results (Audio Interviews & MCQ Batteries)")
        with col_r_ref:
            if st.button("🔄 Refresh", key="refresh_mcq_results", use_container_width=True):
                st.rerun()

        res_aud_tab, res_mcq_tab = st.tabs([
            "🎙️ Adaptive Audio Interviews",
            "📝 Timed MCQ Examination Battery",
        ])

        with res_aud_tab:
            try:
                aud_resp = requests.get(f"{api_base}/api/v1/admin/audio-results", headers=headers, timeout=10)
                if aud_resp.status_code == 200:
                    aud_results = aud_resp.json().get("results", [])
                    if not aud_results:
                        st.info("No Adaptive AI Audio Interviews recorded yet.")
                    else:
                        st.markdown(f"**Total Audio Sessions:** `{len(aud_results)}`")
                        for ar in aud_results:
                            started = datetime.fromtimestamp(ar["started_at"]).strftime("%Y-%m-%d %H:%M") if ar.get("started_at") else "N/A"
                            role_org = ar.get("job_role") or "Software Engineer"
                            if ar.get("company"):
                                role_org += f" @ {ar['company']}"
                            round_lbl = ar.get("interview_round", "Technical")
                            score_lbl = f"{ar['total_score']:.1f}/100 ({ar.get('grade', 'N/A')})" if ar.get("status") == "completed" else "In Progress"
                            st_icon = "✅ Completed" if ar.get("status") == "completed" else "⏳ Active"
                            with st.expander(f"🎙️ {ar['email']} — {role_org} [{round_lbl}] — {score_lbl} ({started})"):
                                st.markdown(f"- **Session ID:** `{ar['session_id']}`")
                                st.markdown(f"- **Candidate Email:** `{ar['email']}`")
                                st.markdown(f"- **Dossier Role / Org:** `{role_org}`")
                                st.markdown(f"- **Interview Round:** `{round_lbl}` (`{ar.get('difficulty', 'medium')}`)")
                                st.markdown(f"- **Questions / Follow-ups:** `{ar.get('questions_asked', 0)}` main, `{ar.get('followups_asked', 0)}` follow-ups")
                                st.markdown(f"- **Score & Grade:** `{score_lbl}`")
                                st.markdown(f"- **Status:** {st_icon}")
                elif aud_resp.status_code == 404:
                    st.error("Audio results endpoint returned 404 — please restart the FastAPI backend (`uvicorn`) to load the updated admin routes.")
                else:
                    detail = aud_resp.json().get("detail", aud_resp.status_code) if aud_resp.headers.get("content-type", "").startswith("application/json") else aud_resp.status_code
                    st.error(f"Failed to fetch audio interview results ({detail}).")
            except Exception as e:
                st.error(f"Error: {str(e)}")

        with res_mcq_tab:
            try:
                resp = requests.get(f"{api_base}/api/v1/admin/results", headers=headers, timeout=10)
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if not results:
                        st.info("No MCQ examinations completed yet.")
                    else:
                        st.markdown(f"**Total MCQ Sessions:** `{len(results)}`")
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
                    st.error("Failed to fetch MCQ results.")
            except Exception as e:
                st.error(f"Error: {str(e)}")

    # === Tab 5: Centralized Question Bank ===
    with tab5:
        col_qb_title, col_qb_ref = st.columns([4, 1])
        with col_qb_title:
            st.markdown("### 🌐 Centralized Question Bank (11 Curricular Topics)")
            st.markdown(
                "Topic-indexed question bank seeded from `data/question_bank/questions.json` "
                "with plain-text normalization, SHA-256 deduplication, and semantic similarity checks."
            )
        with col_qb_ref:
            if st.button("🔄 Refresh Data", key="refresh_scraping_tab", use_container_width=True):
                st.rerun()

        try:
            stats_resp = requests.get(f"{api_base}/api/v1/scraping/stats", headers=headers, timeout=5)
            topics_resp = requests.get(f"{api_base}/api/v1/questions/topics", headers=headers, timeout=5)
            if stats_resp.status_code == 200:
                stats = stats_resp.json()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("📚 Canonical Questions", stats.get("total_canonical", 0))
                m2.metric("🔗 Source Records", stats.get("total_sources", 0))
                m3.metric("🧭 Active Topics", len(stats.get("by_topic", {})))
                m4.metric("🎯 Rounds", ", ".join(stats.get("by_round", {}).keys()) or "None")

                st.markdown("---")
                if topics_resp.status_code == 200 and topics_resp.json().get("topics"):
                    st.markdown("#### 📡 Topic Distribution (Easy / Medium / Hard)")
                    topic_rows = [
                        {
                            "Topic": tp["topic"],
                            "Easy": tp.get("easy_count", 0),
                            "Medium": tp.get("medium_count", 0),
                            "Hard": tp.get("hard_count", 0),
                            "Total": tp.get("question_count", 0),
                            "Rounds": ", ".join(tp.get("rounds", [])),
                        }
                        for tp in topics_resp.json()["topics"]
                    ]
                    st.dataframe(topic_rows, use_container_width=True, hide_index=True)

                c_p1, c_p2 = st.columns(2, gap="medium")
                with c_p1:
                    st.markdown("#### 📊 By Difficulty")
                    for d_name, d_cnt in stats.get("by_difficulty", {}).items():
                        st.write(f"- **{d_name.upper()}**: `{d_cnt}`")
                with c_p2:
                    st.markdown("#### 🎯 By Interview Round")
                    for r_name, r_cnt in stats.get("by_round", {}).items():
                        st.write(f"- **{r_name}**: `{r_cnt}`")
            else:
                st.warning("Could not fetch question bank statistics.")
        except Exception as e:
            st.warning(f"Stats offline: {e}")

        st.markdown("---")
        st.markdown("#### 🛠️ Question Bank Database Seeding")
        if st.button("RE-SYNC SQLITE FROM /data/question_bank/questions.json", type="primary", use_container_width=True):
            try:
                seed_resp = requests.post(
                    f"{api_base}/api/v1/scraping/seed",
                    params={"replace": True},
                    headers=headers,
                    timeout=120,
                )
                if seed_resp.status_code == 200:
                    st.success(f"✅ {seed_resp.json().get('message', 'Question bank synced cleanly to SQLite database.')}")
                    st.rerun()
                else:
                    st.error(f"Sync failed: {seed_resp.text}")
            except Exception as e:
                st.error(f"Sync error: {e}")

    # === Tab 6: Auth & Email OTP Configuration Status ===
    with tab6:
        st.markdown("### 🔐 Authentication & Email OTP Configuration")
        st.markdown("Inspect active OTP delivery mode (`console` vs `email`) and test live SMTP server authentication.")
        try:
            otp_resp = requests.get(f"{api_base}/api/v1/admin/otp-status", headers=headers, timeout=8)
            if otp_resp.status_code == 200:
                cfg = otp_resp.json()
                oc1, oc2, oc3, oc4 = st.columns(4)
                oc1.metric("OTP Delivery Mode", cfg.get("otp_mode", "console").upper())
                oc2.metric("OTP on Sign-In", "ENABLED" if cfg.get("login_require_otp") else "DISABLED")
                oc3.metric("SMTP Host", f"{cfg.get('smtp_host', '')}:{cfg.get('smtp_port', '')}")
                oc4.metric("SMTP Credentials", "READY" if cfg.get("credentials_configured") else "MISSING")

                st.markdown(f"- **Sender Identity:** `{cfg.get('smtp_from_name')}` &lt;`{cfg.get('smtp_from_email') or 'Not set'}`&gt;")
                st.markdown(f"- **SMTP Username:** `{cfg.get('smtp_username_masked') or 'Not set'}`")

                if st.button("🔌 TEST SMTP LOGIN CONNECTION", type="primary", key="admin_test_smtp_btn"):
                    with st.spinner("Testing TLS/SMTP authentication..."):
                        t_resp = requests.post(f"{api_base}/api/v1/admin/test-smtp", headers=headers, timeout=15)
                        if t_resp.status_code == 200:
                            st.success(f"✅ {t_resp.json().get('message', 'SMTP verified.')}")
                        else:
                            detail = t_resp.json().get("detail", t_resp.text) if t_resp.headers.get("content-type", "").startswith("application/json") else t_resp.text
                            st.error(f"❌ {detail}")
            else:
                st.warning("Could not load OTP configuration status.")
        except Exception as e:
            st.error(f"Error inspecting OTP status: {e}")


