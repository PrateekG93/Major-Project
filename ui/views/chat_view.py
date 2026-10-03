"""
Academic Q&A Chat View
=======================
RAG-powered chat interface for asking questions against admin-uploaded course materials.
Displays answers with source citations from textbooks.
"""

import requests
import streamlit as st


def render():
    st.markdown("# 💬 Academic Q&A")
    st.markdown(
        "Ask questions about your course materials. The system searches "
        "through textbooks and lecture notes uploaded by your instructor "
        "and generates grounded answers with citations."
    )

    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")
    token = st.session_state.get("session_token", "")
    headers = {"x-session-token": token}

    # Initialize chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Settings
    with st.expander("⚙️ Settings", expanded=False):
        top_k = st.slider("Context chunks (top_k)", 1, 10, 5)

    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📚 Sources"):
                    for src in msg["sources"]:
                        st.markdown(
                            f"- **{src['document']}** "
                            f"{'| Page: ' + str(src.get('page', '')) if src.get('page') else ''} "
                            f"{'| Section: ' + src.get('section', '') if src.get('section') else ''} "
                            f"(relevance: {src.get('relevance_score', 0):.2f})"
                        )

    # Chat input
    if prompt := st.chat_input("Ask a question about your course materials..."):
        # Add user message to history
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Query the API
        with st.chat_message("assistant"):
            with st.spinner("Searching course materials and generating answer..."):
                try:
                    resp = requests.post(
                        f"{api_base}/api/v1/ask",
                        json={"query": prompt, "top_k": top_k},
                        headers=headers,
                        timeout=120,
                    )

                    if resp.status_code == 200:
                        result = resp.json()
                        st.markdown(result["answer"])

                        sources = result.get("sources", [])
                        if sources:
                            with st.expander("📚 Sources"):
                                for src in sources:
                                    st.markdown(
                                        f"- **{src['document']}** "
                                        f"{'| Page: ' + str(src.get('page', '')) if src.get('page') else ''} "
                                        f"{'| Section: ' + src.get('section', '') if src.get('section') else ''} "
                                        f"(relevance: {src.get('relevance_score', 0):.2f})"
                                    )

                        st.caption(
                            f"Model: {result.get('model_used', 'unknown')} | "
                            f"Chunks retrieved: {result.get('chunks_retrieved', 0)}"
                        )

                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": result["answer"],
                            "sources": sources,
                        })
                    elif resp.status_code == 404:
                        msg = "📭 No course materials found. Please ask your instructor to upload textbooks via the Admin Portal."
                        st.warning(msg)
                        st.session_state.chat_history.append({"role": "assistant", "content": msg})
                    else:
                        error = resp.json().get("detail", "Unknown error")
                        st.error(f"Error: {error}")

                except requests.ConnectionError:
                    st.error(
                        "Cannot connect to the API server. Start it with:\n"
                        "```\npython -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload\n```"
                    )
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    # Clear chat button
    if st.session_state.chat_history:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
