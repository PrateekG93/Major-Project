"""
Mock Interview View (MCQ)
===========================
MCQ-based mock interview with:
- 4 options (A/B/C/D) per question
- 45-second countdown timer per question
- Auto-submit on timeout
- Score display and question review
"""

import time

import requests
import streamlit as st


def render():
    st.markdown("# 🎯 Mock Interview (MCQ)")
    st.markdown(
        "Aptitude-style MCQ questions based on your **Job Description** "
        "and course materials. **45 seconds** per question."
    )

    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")
    token = st.session_state.get("session_token", "")
    headers = {"x-session-token": token}

    # Initialize state
    if "mcq_session" not in st.session_state:
        st.session_state.mcq_session = None
    if "mcq_current_question" not in st.session_state:
        st.session_state.mcq_current_question = None
    if "mcq_question_start" not in st.session_state:
        st.session_state.mcq_question_start = None
    if "mcq_scores" not in st.session_state:
        st.session_state.mcq_scores = []
    if "mcq_show_result" not in st.session_state:
        st.session_state.mcq_show_result = None

    TIME_LIMIT = 45  # seconds

    # === No Active Session: Setup ===
    if st.session_state.mcq_session is None:
        st.markdown("### 📋 Start MCQ Interview")

        # Check if resume and JD are uploaded
        try:
            resp = requests.get(f"{api_base}/api/v1/upload/documents", headers=headers, timeout=10)
            if resp.status_code == 200:
                docs = resp.json()
                resume_ok = docs.get("resume", {}).get("uploaded", False)
                jd_ok = docs.get("jd", {}).get("uploaded", False)

                col1, col2 = st.columns(2)
                with col1:
                    if resume_ok:
                        st.success(f"✅ Resume: {docs['resume'].get('filename', 'uploaded')}")
                    else:
                        st.error("❌ Resume not uploaded")
                with col2:
                    if jd_ok:
                        st.success(f"✅ JD: {docs['jd'].get('filename', 'uploaded')}")
                    else:
                        st.error("❌ JD not uploaded")

                if not resume_ok or not jd_ok:
                    st.warning("⚠️ Please upload both your Resume and JD in the **📄 Upload Documents** section first.")
                    return
            else:
                st.warning("Could not check document status. Please ensure you've uploaded Resume and JD.")
        except requests.ConnectionError:
            st.error("Cannot connect to API server.")
            return
        except Exception:
            pass

        st.markdown("---")
        num_questions = st.slider("Number of Questions", 5, 20, 10, key="mcq_num_q")

        st.info(f"⏱️ Each question has a **{TIME_LIMIT}-second** time limit. Questions are based on your JD and course materials.")

        if st.button("🚀 Start Interview", type="primary", use_container_width=True, key="start_mcq_btn"):
            with st.spinner("Generating MCQ questions from your JD and course materials..."):
                try:
                    resp = requests.post(
                        f"{api_base}/api/v1/mcq/start",
                        json={"num_questions": num_questions},
                        headers=headers,
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        st.session_state.mcq_session = result
                        st.session_state.mcq_current_question = result["first_question"]
                        st.session_state.mcq_question_start = time.time()
                        st.session_state.mcq_scores = []
                        st.session_state.mcq_show_result = None
                        st.rerun()
                    else:
                        detail = resp.json().get("detail", "Failed to start")
                        st.error(f"❌ {detail}")
                except requests.ConnectionError:
                    st.error("Cannot connect to API server.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        return

    # === Active Session ===
    session = st.session_state.mcq_session
    current_q = st.session_state.mcq_current_question

    # Check if session is complete (no more questions)
    if current_q is None:
        _render_completion(session, api_base, headers)
        return

    # Header
    total = session["total_questions"]
    current_idx = current_q["index"] + 1
    answered = len(st.session_state.mcq_scores)

    prog_cols = st.columns([2, 1, 1])
    prog_cols[0].metric("📝 Question", f"{current_idx} / {total}")
    prog_cols[1].metric("✅ Correct", f"{sum(1 for s in st.session_state.mcq_scores if s['is_correct'])}")
    prog_cols[2].metric("📊 Score", f"{sum(1 for s in st.session_state.mcq_scores if s['is_correct'])}/{answered}" if answered else "0/0")

    st.progress(current_idx / total)

    # === Show Previous Result ===
    if st.session_state.mcq_show_result is not None:
        result = st.session_state.mcq_show_result
        if result["is_correct"]:
            st.success(f"✅ Correct! The answer is **{result['correct_answer']}**")
        else:
            st.error(f"❌ Wrong! The correct answer is **{result['correct_answer']}**")
        if result.get("explanation"):
            st.info(f"💡 {result['explanation']}")
        st.markdown("---")
        st.session_state.mcq_show_result = None

    # === Timer ===
    elapsed = time.time() - (st.session_state.mcq_question_start or time.time())
    remaining = max(0, TIME_LIMIT - elapsed)

    if remaining <= 0:
        # Auto-submit on timeout
        _submit_answer(session, current_q, "", True, TIME_LIMIT, api_base, headers)
        return

    # Timer display
    timer_color = "🟢" if remaining > 15 else "🟡" if remaining > 5 else "🔴"
    st.markdown(f"### ⏱️ {timer_color} Time Remaining: **{int(remaining)}s**")

    # === Question Display ===
    st.markdown("---")
    topic = current_q.get("topic", "General")
    difficulty = current_q.get("difficulty", "medium")
    diff_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(difficulty, "⚪")

    st.markdown(
        f"### Q{current_idx} &nbsp; "
        f"<span style='font-size:0.8em;'>| {topic} | {diff_emoji} {difficulty.capitalize()}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(f"**{current_q['question_text']}**")

    # Options as radio buttons
    options = current_q.get("options", [])
    selected = st.radio(
        "Select your answer:",
        options=options,
        key=f"mcq_option_{current_idx}",
        index=None,
    )

    # Submit button
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("✅ Submit Answer", type="primary", use_container_width=True, key=f"submit_mcq_{current_idx}"):
            if selected is None:
                st.warning("Please select an option.")
            else:
                # Extract letter (A, B, C, or D) from the selected option
                answer_letter = selected[0] if selected else ""
                response_time = time.time() - (st.session_state.mcq_question_start or time.time())
                _submit_answer(session, current_q, answer_letter, False, response_time, api_base, headers)
    with col2:
        if st.button("⏭️ Skip", key=f"skip_mcq_{current_idx}"):
            response_time = time.time() - (st.session_state.mcq_question_start or time.time())
            _submit_answer(session, current_q, "", True, response_time, api_base, headers)

    # End early
    st.markdown("---")
    if st.button("⏹️ End Interview Early", key="end_mcq_early"):
        st.session_state.mcq_current_question = None
        st.rerun()


def _submit_answer(session, current_q, answer_letter, is_timeout, response_time, api_base, headers):
    """Submit an MCQ answer to the API."""
    try:
        resp = requests.post(
            f"{api_base}/api/v1/mcq/answer",
            json={
                "session_id": session["session_id"],
                "selected_option": answer_letter,
                "response_time": response_time,
                "is_timeout": is_timeout,
            },
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            result = resp.json()

            # Store score
            st.session_state.mcq_scores.append({
                "is_correct": result["is_correct"],
                "correct_answer": result["correct_answer"],
                "explanation": result.get("explanation", ""),
                "topic": current_q.get("topic", ""),
            })

            # Show result
            st.session_state.mcq_show_result = result

            # Next question or complete
            if result["is_complete"]:
                st.session_state.mcq_current_question = None
            else:
                st.session_state.mcq_current_question = result.get("next_question")
                st.session_state.mcq_question_start = time.time()

            st.rerun()
        else:
            st.error(f"Error: {resp.json().get('detail', 'Submission failed')}")
    except Exception as e:
        st.error(f"Error: {str(e)}")


def _render_completion(session, api_base, headers):
    """Render the interview completion screen."""
    st.success("🎉 Interview Complete!")

    scores = st.session_state.mcq_scores
    total = len(scores)
    correct = sum(1 for s in scores if s["is_correct"])
    percentage = round(correct / max(total, 1) * 100, 1)

    # Score header
    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Total Score", f"{correct}/{total}")
    col2.metric("📈 Percentage", f"{percentage}%")
    grade = "🏆 Excellent" if percentage >= 80 else "✅ Good" if percentage >= 60 else "⚠️ Needs Work" if percentage >= 40 else "❌ Poor"
    col3.metric("🎯 Grade", grade)

    # Topic breakdown
    st.markdown("---")
    st.markdown("### 📊 Topic-wise Performance")
    topic_stats = {}
    for s in scores:
        topic = s.get("topic", "General")
        if topic not in topic_stats:
            topic_stats[topic] = {"correct": 0, "total": 0}
        topic_stats[topic]["total"] += 1
        if s["is_correct"]:
            topic_stats[topic]["correct"] += 1

    for topic, stats in topic_stats.items():
        pct = round(stats["correct"] / stats["total"] * 100, 1)
        emoji = "🟢" if pct >= 70 else "🟡" if pct >= 50 else "🔴"
        st.markdown(f"{emoji} **{topic}**: {stats['correct']}/{stats['total']} ({pct}%)")

    # Question-by-question review
    st.markdown("---")
    st.markdown("### 📝 Question Review")
    for i, s in enumerate(scores, 1):
        icon = "✅" if s["is_correct"] else "❌"
        with st.expander(f"{icon} Q{i} — {s.get('topic', 'General')}"):
            st.markdown(f"**Correct Answer:** {s['correct_answer']}")
            if s.get("explanation"):
                st.info(f"💡 {s['explanation']}")

    # Actions
    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📊 View Dashboard", use_container_width=True, key="goto_dashboard"):
            st.session_state.current_page = "dashboard"
            st.rerun()
    with col_b:
        if st.button("🔄 New Interview", use_container_width=True, key="new_mcq"):
            st.session_state.mcq_session = None
            st.session_state.mcq_current_question = None
            st.session_state.mcq_scores = []
            st.session_state.mcq_show_result = None
            st.rerun()
