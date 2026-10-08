"""
Upload View (Candidate Dossier Desk)
=====================================
Editorial document intake station:
- Asymmetric dual-slot docket (Resume vs Target Job Description)
- Strict monospace metadata chips and verification status
- Real functional edge case handling for empty states and format validation
"""

import requests
import streamlit as st
from ui.theme import render_editorial_title, render_empty_state, render_skeleton_card


def render():
    render_editorial_title(
        title="Dossier Ingestion Desk",
        subtitle="Upload candidate resume and target industry job specification for role-matching analytics.",
        meta_tag="MODULE 01 // INTAKE",
    )

    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")
    token = st.session_state.get("session_token", "")
    headers = {"x-session-token": token}

    # Fetch current documents status
    resume_status = None
    jd_status = None
    try:
        resp = requests.get(f"{api_base}/api/v1/upload/documents", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            resume_status = data.get("resume", {})
            jd_status = data.get("jd", {})
    except Exception:
        pass

    # Status Dockets Bar
    col_stat1, col_stat2 = st.columns(2, gap="medium")
    has_resume = bool(resume_status and resume_status.get("uploaded"))
    has_jd = bool(jd_status and jd_status.get("uploaded"))

    with col_stat1:
        if has_resume:
            st.markdown(
                f"""
                <div class="docket-card" style="border-left-color: #2D5A27;">
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span class="editorial-tag" style="background: rgba(45, 90, 39, 0.1); color: #2D5A27;">STATUS // VERIFIED</span>
                        <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">SLOT: RESUME</span>
                    </div>
                    <h3 style="margin: 0.4rem 0 0.2rem 0; font-family: var(--font-sans);">{resume_status.get('filename', 'Resume Document')}</h3>
                    <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--ink-muted);">
                        VOLUME: {resume_status.get('text_length', 0):,} CHARACTERS • INDEXED IN MEMORY
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="docket-card" style="border-left-color: var(--accent-red);">
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span class="editorial-tag">REQUIRED // MISSING</span>
                        <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">SLOT: RESUME</span>
                    </div>
                    <h3 style="margin: 0.4rem 0 0.2rem 0; font-family: var(--font-sans);">Candidate Resume</h3>
                    <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--ink-muted);">
                        AWAITING INTAKE • COMPLIANT WITH PDF / DOCX / TXT
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_stat2:
        if has_jd:
            st.markdown(
                f"""
                <div class="docket-card" style="border-left-color: #2D5A27;">
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span class="editorial-tag" style="background: rgba(45, 90, 39, 0.1); color: #2D5A27;">STATUS // VERIFIED</span>
                        <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">SLOT: SPECIFICATION</span>
                    </div>
                    <h3 style="margin: 0.4rem 0 0.2rem 0; font-family: var(--font-sans);">{jd_status.get('filename', 'Job Description')}</h3>
                    <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--ink-muted);">
                        VOLUME: {jd_status.get('text_length', 0):,} CHARACTERS • PARSED FOR SKILLS
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="docket-card" style="border-left-color: var(--accent-red);">
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span class="editorial-tag">REQUIRED // MISSING</span>
                        <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">SLOT: SPECIFICATION</span>
                    </div>
                    <h3 style="margin: 0.4rem 0 0.2rem 0; font-family: var(--font-sans);">Job Description (JD)</h3>
                    <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--ink-muted);">
                        AWAITING INTAKE • PASTE TEXT OR UPLOAD FILE
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # Dual Column Intake Workspace
    col_left, col_right = st.columns([1, 1], gap="large")

    # === Column 1: Candidate Resume Intake ===
    with col_left:
        st.markdown(
            """
            <div style="margin-bottom: 0.6rem;">
                <span class="editorial-tag">INTAKE // 01</span>
                <h3 style="margin: 0.3rem 0;">Candidate Resume</h3>
                <p style="font-size: 0.88rem; color: var(--ink-muted);">
                    Upload your latest curriculum vitae. Text parser extracts competency keywords and experience records.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        resume_file = st.file_uploader(
            "Select Resume File",
            type=["pdf", "docx", "txt"],
            help="Supported: PDF, DOCX, TXT (Maximum recommended size: 25MB)",
            key="resume_uploader",
            label_visibility="collapsed",
        )

        if resume_file:
            st.markdown(
                f"""
                <div style="background: var(--bg-paper); border: 1px solid var(--border-subtle); padding: 0.75rem 1rem; border-radius: 4px; margin: 0.5rem 0 0.8rem 0;">
                    <div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">FILE SELECTED</div>
                    <div style="font-family: var(--font-sans); font-size: 0.92rem; font-weight: 600; color: var(--ink-charcoal);">{resume_file.name}</div>
                    <div style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-muted);">{len(resume_file.getvalue()) / 1024:.1f} KB</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("EXECUTE RESUME INTAKE →", type="primary", key="upload_resume_btn", use_container_width=True):
                with st.spinner("Extracting text and isolating skill tokens..."):
                    try:
                        resp = requests.post(
                            f"{api_base}/api/v1/upload/resume",
                            files={"file": (resume_file.name, resume_file.getvalue())},
                            headers=headers,
                            timeout=60,
                        )
                        if resp.status_code == 200:
                            result = resp.json()
                            st.success(f"✅ Ingestion complete. {result['text_length']} characters mapped.")
                            st.rerun()
                        else:
                            st.error(f"❌ {resp.json().get('detail', 'Ingestion failure')}")
                    except requests.ConnectionError:
                        st.error("❌ Backend communication failure. Verify server status.")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

        if has_resume:
            with st.expander("INSPECT EXTRACTED RESUME TEXT", expanded=False):
                st.markdown(
                    f"<div style='font-family: var(--font-mono); font-size: 0.75rem; white-space: pre-wrap; background: var(--bg-paper); padding: 1rem; border-radius: 4px; max-height: 250px; overflow-y: auto;'>{resume_status.get('preview', '')}</div>",
                    unsafe_allow_html=True,
                )

    # === Column 2: Job Description Intake ===
    with col_right:
        st.markdown(
            """
            <div style="margin-bottom: 0.6rem;">
                <span class="editorial-tag">INTAKE // 02</span>
                <h3 style="margin: 0.3rem 0;">Target Job Description</h3>
                <p style="font-size: 0.88rem; color: var(--ink-muted);">
                    Specify target engineering role prerequisites to calibrate mock interview question selection.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        jd_method = st.radio(
            "Input Mode",
            options=["Upload File", "Paste Text"],
            horizontal=True,
            key="jd_method",
            label_visibility="collapsed",
        )

        if jd_method == "Upload File":
            jd_file = st.file_uploader(
                "Select JD Document",
                type=["pdf", "docx", "txt"],
                help="Supported: PDF, DOCX, TXT",
                key="jd_uploader",
                label_visibility="collapsed",
            )
            if jd_file:
                st.markdown(
                    f"""
                    <div style="background: var(--bg-paper); border: 1px solid var(--border-subtle); padding: 0.75rem 1rem; border-radius: 4px; margin: 0.5rem 0 0.8rem 0;">
                        <div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">FILE SELECTED</div>
                        <div style="font-family: var(--font-sans); font-size: 0.92rem; font-weight: 600; color: var(--ink-charcoal);">{jd_file.name}</div>
                        <div style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-muted);">{len(jd_file.getvalue()) / 1024:.1f} KB</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("EXECUTE JD INTAKE →", type="primary", key="upload_jd_file_btn", use_container_width=True):
                    with st.spinner("Parsing job specification..."):
                        try:
                            resp = requests.post(
                                f"{api_base}/api/v1/upload/jd",
                                files={"file": (jd_file.name, jd_file.getvalue())},
                                headers=headers,
                                timeout=60,
                            )
                            if resp.status_code == 200:
                                result = resp.json()
                                st.success(f"✅ Specification parsed. {result['text_length']} characters mapped.")
                                st.rerun()
                            else:
                                st.error(f"❌ {resp.json().get('detail', 'Upload failed')}")
                        except requests.ConnectionError:
                            st.error("❌ Backend communication failure.")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
        else:
            jd_text = st.text_area(
                "Paste Job Description text",
                height=180,
                placeholder="Paste responsibilities, required skills, and qualification notes here...",
                key="jd_text_input",
                label_visibility="collapsed",
            )
            if st.button("STORE JD SPECIFICATION →", type="primary", key="upload_jd_text_btn", use_container_width=True):
                if not jd_text or not jd_text.strip():
                    st.error("Please enter job description text before submitting.")
                else:
                    with st.spinner("Recording specification..."):
                        try:
                            resp = requests.post(
                                f"{api_base}/api/v1/upload/jd",
                                data={"jd_text": jd_text},
                                headers=headers,
                                timeout=30,
                            )
                            if resp.status_code == 200:
                                result = resp.json()
                                st.success(f"✅ Specification stored. {result['text_length']} characters.")
                                st.rerun()
                            else:
                                st.error(f"❌ {resp.json().get('detail', 'Ingestion failed')}")
                        except requests.ConnectionError:
                            st.error("❌ Backend communication failure.")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

        if has_jd:
            with st.expander("INSPECT STORED JOB SPECIFICATION", expanded=False):
                st.markdown(
                    f"<div style='font-family: var(--font-mono); font-size: 0.75rem; white-space: pre-wrap; background: var(--bg-paper); padding: 1rem; border-radius: 4px; max-height: 250px; overflow-y: auto;'>{jd_status.get('preview', '')}</div>",
                    unsafe_allow_html=True,
                )
