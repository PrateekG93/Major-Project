"""
Academic Q&A Chat View (Scholarly Consultation Desk)
=====================================================
RAG-powered interactive discourse against syllabus textbooks:
- High typographic contrast with structured citation cards
- Strict monospace metadata stamps for retrieval scores and model provenance
- Real functional edge cases with scholarly starter prompts and empty states
"""

import requests
import streamlit as st
from ui.theme import render_editorial_title, render_empty_state


def render():
    render_editorial_title(
        title="Curriculum Consultation Desk",
        subtitle="Inquire against official textbooks and lecture modules. Grounded responses cite primary course texts.",
        meta_tag="MODULE 02 // HYBRID RAG",
    )

    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")
    token = st.session_state.get("session_token", "")
    headers = {"x-session-token": token}

    # Initialize chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Controls Bar
    col_ctrl, col_act = st.columns([4, 1], gap="medium")
    with col_ctrl:
        with st.expander("RETRIEVAL TELEMETRY & CHUNK SETTINGS", expanded=False):
            top_k = st.slider("Passage Count (top_k chunks)", min_value=1, max_value=10, value=5)
    with col_act:
        if st.session_state.chat_history:
            if st.button("PURGE DISCOURSE", use_container_width=True, type="secondary"):
                st.session_state.chat_history = []
                st.rerun()

    # Empty State with Scholarly Starter Questions
    if not st.session_state.chat_history:
        render_empty_state(
            title="Awaiting Curricular Inquiries",
            message="Pose specific conceptual, algorithmic, or theoretical questions grounded in your course documents.",
            meta_code="CONSULTATION // READY",
        )

        st.markdown(
            """
            <div style="margin-top: 1.5rem; margin-bottom: 0.6rem;">
                <span class="editorial-tag">PROMPT INSPIRATION // SAMPLE QUERIES</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        sample_prompts = [
            "What is the mathematical formulation of the Bias-Variance tradeoff?",
            "Explain ACID properties in transactional relational databases.",
            "How does Principal Component Analysis compute orthogonal axes of variance?",
        ]

        cols = st.columns(len(sample_prompts))
        for idx, prompt_text in enumerate(sample_prompts):
            with cols[idx]:
                if st.button(prompt_text, key=f"sample_prompt_{idx}", use_container_width=True, type="secondary"):
                    st.session_state["queued_prompt"] = prompt_text
                    st.rerun()

    # Display chat history
    for msg in st.session_state.chat_history:
        role = msg["role"]
        content = msg["content"]
        sources = msg.get("sources", [])
        model_used = msg.get("model_used", "")

        if role == "user":
            st.markdown(
                f"""
                <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: 4px; padding: 1rem 1.25rem; margin-bottom: 1rem; border-left: 3px solid var(--ink-charcoal);">
                    <div style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-tertiary); letter-spacing: 0.08em; text-transform: uppercase;">
                        STUDENT INQUIRY
                    </div>
                    <div style="font-family: var(--font-sans); font-size: 0.98rem; color: var(--ink-charcoal); margin-top: 0.35rem; font-weight: 500;">
                        {content}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div style="background: var(--bg-paper); border: 1px solid var(--border-subtle); border-radius: 4px; padding: 1.25rem 1.35rem; margin-bottom: 1rem; border-left: 3px solid var(--accent-red);">
                    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.5rem;">
                        <span class="editorial-tag">GROUNDED ANSWER</span>
                        <span style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-tertiary);">
                            PROVENANCE: {model_used.upper() if model_used else 'RAG ENGINE'}
                        </span>
                    </div>
                    <div style="font-family: var(--font-sans); font-size: 0.96rem; color: var(--ink-charcoal); line-height: 1.7;">
                        {content}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if sources:
                with st.expander(f"INSPECT {len(sources)} PRIMARY CITATIONS", expanded=False):
                    for s_idx, src in enumerate(sources, 1):
                        pg_info = f" | Page {src['page']}" if src.get("page") else ""
                        sec_info = f" | Section: {src['section']}" if src.get("section") else ""
                        score_info = f"{src.get('relevance_score', 0):.2f}"
                        st.markdown(
                            f"""
                            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: 4px; padding: 0.6rem 0.9rem; margin-bottom: 0.45rem;">
                                <div style="display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 0.72rem;">
                                    <span style="color: var(--ink-charcoal); font-weight: 600;">[{s_idx}] {src['document']}{pg_info}{sec_info}</span>
                                    <span style="color: var(--accent-red);">CONFIDENCE: {score_info}</span>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

    # Process queued or new prompt
    input_prompt = st.chat_input("Enter scholarly question regarding ingested syllabus modules...")
    active_prompt = None

    if st.session_state.get("queued_prompt"):
        active_prompt = st.session_state.pop("queued_prompt")
    elif input_prompt:
        active_prompt = input_prompt

    if active_prompt:
        st.session_state.chat_history.append({"role": "user", "content": active_prompt})

        with st.spinner("Searching vector index and synthesizing grounded explanation..."):
            try:
                top_k_val = top_k if 'top_k' in locals() else 5
                resp = requests.post(
                    f"{api_base}/api/v1/ask",
                    json={"query": active_prompt, "top_k": top_k_val},
                    headers=headers,
                    timeout=120,
                )

                if resp.status_code == 200:
                    result = resp.json()
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": result["answer"],
                        "sources": result.get("sources", []),
                        "model_used": result.get("model_used", "Groq LPU"),
                    })
                    st.rerun()
                elif resp.status_code == 404:
                    msg = "No course materials are currently indexed. Request your faculty administrator to upload course packs."
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": msg,
                        "sources": [],
                        "model_used": "SYSTEM",
                    })
                    st.rerun()
                else:
                    err_msg = resp.json().get("detail", "Error retrieving context")
                    st.error(f"❌ Retrieval failure: {err_msg}")
            except requests.ConnectionError:
                st.error("❌ Backend server unreachable at http://127.0.0.1:8000.")
            except Exception as e:
                st.error(f"Error: {str(e)}")
