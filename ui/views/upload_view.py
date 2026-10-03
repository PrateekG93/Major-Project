"""
Upload View (Resume + JD)
===========================
Two-slot upload interface:
- Resume (PDF/DOCX/TXT)
- Job Description (PDF/DOCX/TXT or paste text)
Shows status badges and parsed previews.
"""

import requests
import streamlit as st


def render():
    st.markdown("# 📄 Upload Documents")
    st.markdown(
        "Upload your **Resume** and **Job Description (JD)**. "
        "These will be used across the Mock Interview and Performance Dashboard."
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

    # Status badges
    st.markdown("### 📋 Document Status")
    col1, col2 = st.columns(2)

    with col1:
        if resume_status and resume_status.get("uploaded"):
            st.success(f"✅ Resume: **{resume_status.get('filename', 'uploaded')}** ({resume_status.get('text_length', 0)} chars)")
        else:
            st.warning("⚠️ Resume: Not uploaded")

    with col2:
        if jd_status and jd_status.get("uploaded"):
            st.success(f"✅ JD: **{jd_status.get('filename', 'uploaded')}** ({jd_status.get('text_length', 0)} chars)")
        else:
            st.warning("⚠️ JD: Not uploaded")

    st.markdown("---")

    # === Resume Upload ===
    st.markdown("### 📝 Upload Resume")
    resume_file = st.file_uploader(
        "Choose your resume",
        type=["pdf", "docx", "txt"],
        help="Supported: PDF, DOCX, TXT",
        key="resume_uploader",
    )

    if resume_file:
        st.metric("📁 File", resume_file.name)
        if st.button("🚀 Upload Resume", type="primary", key="upload_resume_btn"):
            with st.spinner("Parsing resume..."):
                try:
                    resp = requests.post(
                        f"{api_base}/api/v1/upload/resume",
                        files={"file": (resume_file.name, resume_file.getvalue())},
                        headers=headers,
                        timeout=60,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        st.success(f"✅ Resume uploaded! ({result['text_length']} characters extracted)")
                        with st.expander("📖 Preview"):
                            st.text(result.get("preview", ""))
                        st.rerun()
                    else:
                        st.error(f"❌ {resp.json().get('detail', 'Upload failed')}")
                except requests.ConnectionError:
                    st.error("Cannot connect to API server.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    st.markdown("---")

    # === JD Upload ===
    st.markdown("### 💼 Upload Job Description")

    jd_method = st.radio(
        "How would you like to provide the JD?",
        options=["📄 Upload File", "📝 Paste Text"],
        horizontal=True,
        key="jd_method",
    )

    if jd_method == "📄 Upload File":
        jd_file = st.file_uploader(
            "Choose JD file",
            type=["pdf", "docx", "txt"],
            help="Supported: PDF, DOCX, TXT",
            key="jd_uploader",
        )
        if jd_file:
            if st.button("🚀 Upload JD", type="primary", key="upload_jd_file_btn"):
                with st.spinner("Parsing JD..."):
                    try:
                        resp = requests.post(
                            f"{api_base}/api/v1/upload/jd",
                            files={"file": (jd_file.name, jd_file.getvalue())},
                            headers=headers,
                            timeout=60,
                        )
                        if resp.status_code == 200:
                            result = resp.json()
                            st.success(f"✅ JD uploaded! ({result['text_length']} characters)")
                            st.rerun()
                        else:
                            st.error(f"❌ {resp.json().get('detail', 'Upload failed')}")
                    except requests.ConnectionError:
                        st.error("Cannot connect to API server.")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
    else:
        jd_text = st.text_area(
            "Paste Job Description",
            height=250,
            placeholder="Paste the full job description here...",
            key="jd_text_input",
        )
        if st.button("🚀 Save JD", type="primary", key="upload_jd_text_btn"):
            if not jd_text or not jd_text.strip():
                st.error("Please paste the JD text.")
            else:
                with st.spinner("Saving JD..."):
                    try:
                        resp = requests.post(
                            f"{api_base}/api/v1/upload/jd",
                            data={"jd_text": jd_text},
                            headers=headers,
                            timeout=30,
                        )
                        if resp.status_code == 200:
                            result = resp.json()
                            st.success(f"✅ JD saved! ({result['text_length']} characters)")
                            st.rerun()
                        else:
                            st.error(f"❌ {resp.json().get('detail', 'Upload failed')}")
                    except requests.ConnectionError:
                        st.error("Cannot connect to API server.")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

    # === Preview Current Documents ===
    if resume_status and resume_status.get("uploaded"):
        st.markdown("---")
        with st.expander("📖 Current Resume Preview"):
            st.text(resume_status.get("preview", "No preview available"))

    if jd_status and jd_status.get("uploaded"):
        with st.expander("💼 Current JD Preview"):
            st.text(jd_status.get("preview", "No preview available"))
