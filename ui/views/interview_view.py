"""
Mock Interview View (Precision Technical Assessment Terminal)
==============================================================
MCQ-based timed assessment:
- Examination docket presentation
- Weighted countdown progress telemetry
- Clean lettered option selection with immediate feedback
- Diagnostic performance summary with letter grades
"""

import time
import requests
import streamlit as st
from ui.theme import render_editorial_title, render_empty_state


def render():
    render_editorial_title(
        title="Technical Assessment Terminal",
        subtitle="45-second timed aptitude & domain inquisition mapped directly to your Target Job Description.",
        meta_tag="MODULE 03 // VIVA TERMINAL",
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
        # Check prerequisites
        try:
            resp = requests.get(f"{api_base}/api/v1/upload/documents", headers=headers, timeout=10)
            if resp.status_code == 200:
                docs = resp.json()
                resume_ok = docs.get("resume", {}).get("uploaded", False)
                jd_ok = docs.get("jd", {}).get("uploaded", False)

                if not resume_ok or not jd_ok:
                    render_empty_state(
                        title="Dossier Prerequisite Required",
                        message="Please upload both your Resume and Target Job Description in Section 01 before initiating a technical interview session.",
                        meta_code="GATEWAY // PREREQUISITE",
                    )
                    if st.button("PROCEED TO DOSSIER UPLOAD →", type="primary", use_container_width=True):
                        st.session_state.current_page = "upload"
                        st.rerun()
                    return
            else:
                st.warning("⚠️ Document status verification inconclusive.")
        except requests.ConnectionError:
            st.error("❌ Backend server unreachable at http://127.0.0.1:8000.")
            return
        except Exception:
            pass

        # Session Configuration Card
        st.markdown(
            """
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.5rem; border-radius: 6px; margin: 1rem 0;">
                <div style="display: flex; justify-content: space-between; align-items: baseline;">
                    <span class="editorial-tag">SESSION SPECIFICATION</span>
                    <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">CADENCE: 45 SEC / QUESTION</span>
                </div>
                <h3 style="margin: 0.5rem 0 0.2rem 0;">Calibrate Examination Battery</h3>
                <p style="font-size: 0.88rem; color: var(--ink-muted);">
                    Questions are dynamically synthesized from your job description and grounded against course materials.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        num_questions = st.slider("Battery Size (Total Questions)", min_value=5, max_value=20, value=10, key="mcq_num_q")

        if st.button("INITIALIZE EXAMINATION BATTERY →", type="primary", use_container_width=True, key="start_mcq_btn"):
            with st.spinner("Synthesizing questions via Groq LPU and aligning with curriculum..."):
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
                        detail = resp.json().get("detail", "Initialization failed")
                        st.error(f"❌ {detail}")
                except requests.ConnectionError:
                    st.error("❌ Cannot communicate with API service.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        return

    # === Active Session ===
    session = st.session_state.mcq_session
    current_q = st.session_state.mcq_current_question

    if current_q is None:
        _render_completion(session, api_base, headers)
        return

    # Header Telemetry
    total = session["total_questions"]
    current_idx = current_q["index"] + 1
    answered = len(st.session_state.mcq_scores)
    correct_count = sum(1 for s in st.session_state.mcq_scores if s["is_correct"])

    prog_cols = st.columns([2, 1, 1], gap="medium")
    with prog_cols[0]:
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.75rem 1rem; border-radius: 4px;">
                <div style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-tertiary); text-transform: uppercase;">BATTERY PROGRESS</div>
                <div style="font-family: var(--font-serif); font-size: 1.6rem; color: var(--ink-charcoal);">QUESTION {current_idx} OF {total}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with prog_cols[1]:
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.75rem 1rem; border-radius: 4px;">
                <div style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-tertiary); text-transform: uppercase;">VERIFIED CORRECT</div>
                <div style="font-family: var(--font-serif); font-size: 1.6rem; color: #2D5A27;">{correct_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with prog_cols[2]:
        acc_pct = f"{round(correct_count / answered * 100)}%" if answered else "N/A"
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.75rem 1rem; border-radius: 4px;">
                <div style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-tertiary); text-transform: uppercase;">ACCURACY RATE</div>
                <div style="font-family: var(--font-serif); font-size: 1.6rem; color: var(--ink-charcoal);">{acc_pct}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Progress bar
    st.progress(current_idx / total)

    # Previous Result Notification
    if st.session_state.mcq_show_result is not None:
        result = st.session_state.mcq_show_result
        if result["is_correct"]:
            st.markdown(
                f"""
                <div style="background: rgba(45, 90, 39, 0.08); border: 1px solid #2D5A27; border-radius: 4px; padding: 0.8rem 1rem; margin: 0.8rem 0;">
                    <span style="font-family: var(--font-mono); font-size: 0.72rem; color: #2D5A27; font-weight: 700;">PREVIOUS ANSWER: ACCURATE</span>
                    <div style="font-size: 0.9rem; color: #141413; margin-top: 2px;">{result.get('explanation', '')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div style="background: rgba(217, 56, 30, 0.08); border: 1px solid var(--accent-red); border-radius: 4px; padding: 0.8rem 1rem; margin: 0.8rem 0;">
                    <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--accent-red); font-weight: 700;">PREVIOUS ANSWER: DEFICIENT (CORRECT OPTION: {result['correct_answer']})</span>
                    <div style="font-size: 0.9rem; color: #141413; margin-top: 2px;">{result.get('explanation', '')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.session_state.mcq_show_result = None

    # Timer Calculation
    elapsed = time.time() - (st.session_state.mcq_question_start or time.time())
    remaining = max(0, TIME_LIMIT - elapsed)

    if remaining <= 0:
        _submit_answer(session, current_q, "", True, TIME_LIMIT, api_base, headers)
        return

    # Visual Timer Strip
    timer_urgency = "var(--accent-red)" if remaining < 10 else "var(--ink-charcoal)"
    st.markdown(
        f"""
        <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.6rem 1rem; border-radius: 4px; margin-top: 0.8rem;">
            <span style="font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.06em; color: var(--ink-tertiary);">CADENCE CLOCK</span>
            <span style="font-family: var(--font-mono); font-size: 1rem; font-weight: 700; color: {timer_urgency};">
                00:{int(remaining):02d}s REMAINING
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Question Docket
    topic = current_q.get("topic", "Computer Science")
    difficulty = current_q.get("difficulty", "medium")

    st.markdown(
        f"""
        <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(20, 20, 19, 0.03);">
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.8rem;">
                <span class="editorial-tag">TOPIC // {topic.upper()}</span>
                <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary); text-transform: uppercase;">
                    COMPLEXITY: {difficulty.upper()}
                </span>
            </div>
            <h3 style="font-family: var(--font-sans); font-size: 1.15rem; font-weight: 600; line-height: 1.5; color: var(--ink-charcoal); margin: 0;">
                {current_q['question_text']}
            </h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    options = current_q.get("options", [])
    selected = st.radio(
        "Select your answer:",
        options=options,
        key=f"mcq_option_{current_idx}",
        index=None,
        label_visibility="collapsed",
    )

    col1, col2 = st.columns([3, 1], gap="medium")
    with col1:
        if st.button("CONFIRM SELECTION →", type="primary", use_container_width=True, key=f"submit_mcq_{current_idx}"):
            if selected is None:
                st.warning("Select an option prior to submitting.")
            else:
                answer_letter = selected[0] if selected else ""
                response_time = time.time() - (st.session_state.mcq_question_start or time.time())
                _submit_answer(session, current_q, answer_letter, False, response_time, api_base, headers)
    with col2:
        if st.button("PASS / SKIP", key=f"skip_mcq_{current_idx}", use_container_width=True, type="secondary"):
            response_time = time.time() - (st.session_state.mcq_question_start or time.time())
            _submit_answer(session, current_q, "", True, response_time, api_base, headers)

    st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
    if st.button("TERMINATE SESSION PREMATURELY", key="end_mcq_early", type="secondary"):
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
            st.session_state.mcq_scores.append({
                "is_correct": result["is_correct"],
                "correct_answer": result["correct_answer"],
                "explanation": result.get("explanation", ""),
                "topic": current_q.get("topic", ""),
            })
            st.session_state.mcq_show_result = result
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
    """Render the interview completion report."""
    scores = st.session_state.mcq_scores
    total = len(scores)
    correct = sum(1 for s in scores if s["is_correct"])
    percentage = round(correct / max(total, 1) * 100, 1)

    st.markdown(
        """
        <div class="editorial-header-banner" style="margin-top: 1rem;">
            <div>
                <span class="editorial-tag" style="background: rgba(45, 90, 39, 0.1); color: #2D5A27;">STATUS // COMPLETED</span>
                <h1 style="margin: 0.3rem 0 0 0;">Assessment Concluded</h1>
            </div>
            <div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary); text-align: right;">
                BATTERY RECORD ARCHIVED
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Score Cards
    col1, col2, col3 = st.columns(3, gap="medium")
    with col1:
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.25rem; border-radius: 4px;">
                <div style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-tertiary); text-transform: uppercase;">RAW TALLY</div>
                <div style="font-family: var(--font-serif); font-size: 2.4rem; color: var(--ink-charcoal); line-height: 1.1;">{correct} / {total}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.25rem; border-radius: 4px;">
                <div style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-tertiary); text-transform: uppercase;">ACCURACY PERCENTILE</div>
                <div style="font-family: var(--font-serif); font-size: 2.4rem; color: var(--ink-charcoal); line-height: 1.1;">{percentage}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        grade_label = "HONORS (A+)" if percentage >= 85 else "PROFICIENT (A)" if percentage >= 70 else "DEVELOPING (B)" if percentage >= 50 else "CRITICAL ATTENTION"
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.25rem; border-radius: 4px;">
                <div style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-tertiary); text-transform: uppercase;">DIAGNOSTIC STATUS</div>
                <div style="font-family: var(--font-mono); font-size: 1.1rem; font-weight: 700; color: var(--accent-red); margin-top: 0.5rem;">{grade_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Topic breakdown
    st.markdown("---")
    st.markdown("### Topic-Level Breakdown")
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
        badge_style = "background: rgba(45, 90, 39, 0.1); color: #2D5A27;" if pct >= 70 else "background: rgba(217, 56, 30, 0.1); color: var(--accent-red);"
        st.markdown(
            f"""
            <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.7rem 1.1rem; border-radius: 4px; margin-bottom: 0.5rem;">
                <span style="font-family: var(--font-sans); font-weight: 600; color: var(--ink-charcoal);">{topic}</span>
                <span style="font-family: var(--font-mono); font-size: 0.8rem; padding: 2px 8px; border-radius: 3px; {badge_style}">
                    {stats['correct']}/{stats['total']} ({pct}%)
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Question review
    st.markdown("---")
    with st.expander("INSPECT DETAILED QUESTION TELEMETRY", expanded=False):
        for i, s in enumerate(scores, 1):
            status_text = "CORRECT" if s["is_correct"] else "INCORRECT"
            color = "#2D5A27" if s["is_correct"] else "var(--accent-red)"
            st.markdown(
                f"""
                <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 0.6rem;">
                    <div style="display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 0.72rem;">
                        <span style="color: var(--ink-charcoal); font-weight: 600;">ITEM #{i} — {s.get('topic', 'General')}</span>
                        <span style="color: {color}; font-weight: 700;">{status_text} (BENCHMARK: {s['correct_answer']})</span>
                    </div>
                    <div style="font-size: 0.88rem; color: var(--ink-muted); margin-top: 4px;">{s.get('explanation', '')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    col_a, col_b = st.columns(2, gap="medium")
    with col_a:
        if st.button("PROCEED TO ANALYTICAL DASHBOARD →", use_container_width=True, type="primary", key="goto_dashboard"):
            st.session_state.current_page = "dashboard"
            st.rerun()
    with col_b:
        if st.button("INITIALIZE FRESH SESSION", use_container_width=True, type="secondary", key="new_mcq"):
            st.session_state.mcq_session = None
            st.session_state.mcq_current_question = None
            st.session_state.mcq_scores = []
            st.session_state.mcq_show_result = None
            st.rerun()
