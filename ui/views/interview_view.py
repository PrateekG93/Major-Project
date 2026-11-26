"""
Mock Interview View (Technical Assessment Terminal)
===================================================
Dual-mode technical assessment:
1. AI Audio Interview (Adaptive speech interview via BeFluent engine & Groq LLM)
2. Timed MCQ Examination Battery (Domain aptitude, structured cards, cadence clock)
"""

import html
import re
import time
import requests
import streamlit as st
from ui.theme import render_editorial_title, render_empty_state, render_question_card
from src.utils.text_utils import strip_html_markup


def render():
    render_editorial_title(
        title="Technical Assessment Terminal",
        subtitle="Adaptive technical evaluation calibrated directly to your target role and course dossier.",
        meta_tag="MODULE 03 // MOCK INTERVIEW",
    )

    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")
    token = st.session_state.get("session_token", "")
    headers = {"x-session-token": token}

    # Tab navigation for Assessment Modes
    mode_tab1, mode_tab2 = st.tabs([
        "01 — AI Audio Interview (Adaptive)",
        "02 — Timed MCQ Examination Battery",
    ])

    with mode_tab1:
        from ui.views.audio_interview_panel import render_audio_interview_mode
        render_audio_interview_mode(api_base, headers)

    with mode_tab2:
        _render_mcq_mode(api_base, headers)


# =====================================================================
#  SECTION 1: TIMED MCQ EXAMINATION BATTERY
# =====================================================================

def _normalize_options(raw_options: list) -> tuple[list[str], dict[str, str]]:
    """
    Normalizes any list of options into clean 'A. <text>', 'B. <text>' format.
    Returns:
        (display_options, letter_map)
    where letter_map maps the display string back to the canonical letter ('A', 'B', etc.).
    """
    letters = ["A", "B", "C", "D"]
    if not raw_options or not isinstance(raw_options, list):
        raw_options = ["Option A", "Option B", "Option C", "Option D"]

    # Ensure at least 2 options, pad with dummy if needed
    cleaned_options = list(raw_options)
    while len(cleaned_options) < 4:
        cleaned_options.append(f"Option {letters[len(cleaned_options)]}")

    display_options = []
    letter_map = {}

    for i, opt in enumerate(cleaned_options[:4]):
        letter = letters[i]
        opt_str = strip_html_markup(opt)

        # Strip any existing letter prefix like 'A.', 'A)', '(A)', '[A]', 'Option A:'
        clean_text = re.sub(
            r"^(?:option\s*)?[A-Da-d][\.\)\:\-\s]+|^\[[A-Da-d]\]\s*|^\([A-Da-d]\)\s*",
            "",
            opt_str,
            flags=re.IGNORECASE,
        ).strip()

        if not clean_text:
            clean_text = opt_str

        formatted_display = f"{letter}.  {clean_text}"
        display_options.append(formatted_display)
        letter_map[formatted_display] = letter

    return display_options, letter_map


def _render_mcq_mode(api_base: str, headers: dict):
    """Render the MCQ Timed Assessment Mode."""
    # Initialize MCQ session state
    if "mcq_session" not in st.session_state:
        st.session_state.mcq_session = None
    if "mcq_current_question" not in st.session_state:
        st.session_state.mcq_current_question = None
    if "mcq_question_start" not in st.session_state:
        st.session_state.mcq_question_start = None
    if "mcq_scores" not in st.session_state:
        st.session_state.mcq_scores = []
    if "mcq_last_feedback" not in st.session_state:
        st.session_state.mcq_last_feedback = None
    if "mcq_time_limit" not in st.session_state:
        st.session_state.mcq_time_limit = 45

    # Check if there is an in-progress session in DB to resume
    if st.session_state.mcq_session is None:
        _render_mcq_setup(api_base, headers)
        return

    # Active MCQ Session
    session = st.session_state.mcq_session
    current_q = st.session_state.mcq_current_question

    if current_q is None:
        _render_mcq_completion(session, api_base, headers)
        return

    _render_mcq_question_area(session, current_q, api_base, headers)


def _render_mcq_setup(api_base: str, headers: dict):
    """Render the configuration screen before starting an MCQ session."""
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
                    message="Please upload both your Resume and Target Job Description in Section 01 to calibrate questions to your profile.",
                    meta_code="GATEWAY // PREREQUISITE",
                )
                if st.button("PROCEED TO DOSSIER UPLOAD →", type="primary", use_container_width=True, key="mcq_goto_upload"):
                    st.session_state.current_page = "upload"
                    st.rerun()
                return
    except requests.ConnectionError:
        st.error("❌ Backend server unreachable at http://127.0.0.1:8000.")
        return
    except Exception:
        pass

    # Check for recent incomplete session that can be resumed
    try:
        sess_resp = requests.get(f"{api_base}/api/v1/mcq/sessions", headers=headers, timeout=5)
        if sess_resp.status_code == 200:
            all_sessions = sess_resp.json().get("sessions", [])
            in_progress = [s for s in all_sessions if not s.get("is_complete", 0)]
            if in_progress:
                latest_incomplete = in_progress[0]
                sid = latest_incomplete["session_id"]
                answered = latest_incomplete.get("total_answered", 0)
                total = latest_incomplete.get("num_questions", 10)

                st.markdown(
                    f"""
                    <div style="background: rgba(26, 115, 232, 0.06); border: 1px solid #1a73e8; border-radius: 6px; padding: 1.1rem 1.3rem; margin-bottom: 1.2rem;">
                        <div style="display: flex; justify-content: space-between; align-items: baseline;">
                            <span class="editorial-tag" style="background: rgba(26, 115, 232, 0.12); color: #1a73e8;">RESUME IN-PROGRESS BATTERY</span>
                            <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">SESSION: {sid}</span>
                        </div>
                        <h4 style="margin: 0.4rem 0 0.2rem 0; font-family: var(--font-sans);">Unfinished Assessment Found ({answered}/{total} Answered)</h4>
                        <p style="font-size: 0.88rem; color: var(--ink-muted); margin: 0;">
                            You have an active examination session. You can seamlessly resume where you left off or calibrate a fresh session below.
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                col_res1, col_res2 = st.columns(2, gap="medium")
                with col_res1:
                    if st.button("RESUME SESSION →", type="primary", use_container_width=True, key=f"resume_{sid}"):
                        _resume_session(sid, api_base, headers)
                        return
                with col_res2:
                    if st.button("DISCARD & START FRESH", type="secondary", use_container_width=True, key=f"discard_{sid}"):
                        pass
    except Exception:
        pass

    # Session Configuration Card
    st.markdown(
        '<div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.5rem; border-radius: 6px; margin: 1rem 0;">'
        '<div style="display: flex; justify-content: space-between; align-items: baseline;">'
        '<span class="editorial-tag">SESSION SPECIFICATION</span>'
        '<span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">CADENCE-CONTROLLED</span>'
        '</div>'
        '<h3 style="margin: 0.5rem 0 0.2rem 0;">Calibrate Examination Battery</h3>'
        '<p style="font-size: 0.88rem; color: var(--ink-muted);">'
        "Aptitude and domain-specific questions synthesized from official curriculum textbooks and candidate competencies."
        "</p></div>",
        unsafe_allow_html=True,
    )

    col_cfg2, col_cfg3 = st.columns([1, 1], gap="medium")
    with col_cfg2:
        num_questions = st.slider("Battery Size", min_value=5, max_value=20, value=10, key="mcq_num_q")
    with col_cfg3:
        cadence_choice = st.selectbox(
            "Cadence Clock",
            options=["45 Seconds", "60 Seconds", "90 Seconds", "Untimed Practice"],
            index=0,
            key="mcq_cadence_select",
            help="Select the timer pacing per question.",
        )
        cadence_seconds_map = {
            "45 Seconds": 45,
            "60 Seconds": 60,
            "90 Seconds": 90,
            "Untimed Practice": 0,
        }
        st.session_state.mcq_time_limit = cadence_seconds_map[cadence_choice]

    if st.button("INITIALIZE EXAMINATION BATTERY →", type="primary", use_container_width=True, key="start_mcq_btn"):
        with st.spinner("Synthesizing questions via Groq LPU and aligning with curriculum topics..."):
            try:
                payload = {"num_questions": num_questions}

                resp = requests.post(
                    f"{api_base}/api/v1/mcq/start",
                    json=payload,
                    headers=headers,
                    timeout=120,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    st.session_state.mcq_session = result
                    st.session_state.mcq_current_question = result["first_question"]
                    st.session_state.mcq_question_start = time.time()
                    st.session_state.mcq_scores = []
                    st.session_state.mcq_last_feedback = None
                    st.rerun()
                else:
                    detail = resp.json().get("detail", "Initialization failed")
                    st.error(f"❌ {detail}")
            except requests.ConnectionError:
                st.error("❌ Cannot communicate with API service.")
            except Exception as e:
                st.error(f"Error: {str(e)}")


def _resume_session(session_id: str, api_base: str, headers: dict):
    """Resume an active in-progress MCQ session."""
    try:
        resp = requests.get(f"{api_base}/api/v1/mcq/session/{session_id}", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            st.session_state.mcq_session = {
                "session_id": data["session_id"],
                "total_questions": data["total_questions"],
                "topics": data.get("topics", []),
            }
            st.session_state.mcq_current_question = data.get("current_question")
            st.session_state.mcq_question_start = time.time()
            st.session_state.mcq_scores = data.get("scores", [])
            st.session_state.mcq_last_feedback = None
            st.rerun()
        else:
            st.error("Could not resume session from server.")
    except Exception as e:
        st.error(f"Error resuming session: {e}")


def _render_mcq_question_area(session: dict, current_q: dict, api_base: str, headers: dict):
    """Render the active question docket with clean options and timing controls."""
    total = session.get("total_questions", 10)
    current_idx = current_q.get("index", 0) + 1
    scores = st.session_state.mcq_scores
    answered = len(scores)
    correct_count = sum(1 for s in scores if s.get("is_correct"))

    # Telemetry Bar
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
    st.progress(min(1.0, current_idx / max(total, 1)))

    # Persistent Previous Result Notification
    if st.session_state.mcq_last_feedback is not None:
        fb = st.session_state.mcq_last_feedback
        clean_expl = html.escape(strip_html_markup(fb.get("explanation", "")))
        if fb.get("is_correct"):
            st.markdown(
                (
                    '<div style="background: rgba(45, 90, 39, 0.08); border: 1px solid #2D5A27; border-radius: 4px; padding: 0.8rem 1rem; margin: 0.8rem 0;">'
                    '<span style="font-family: var(--font-mono); font-size: 0.72rem; color: #2D5A27; font-weight: 700;">PREVIOUS ANSWER: ACCURATE</span>'
                    f'<div style="font-size: 0.9rem; color: #141413; margin-top: 2px;">{clean_expl}</div>'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
        else:
            correct_opt = html.escape(str(fb.get("correct_answer", "")))
            st.markdown(
                (
                    '<div style="background: rgba(217, 56, 30, 0.08); border: 1px solid var(--accent-red); border-radius: 4px; padding: 0.8rem 1rem; margin: 0.8rem 0;">'
                    f'<span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--accent-red); font-weight: 700;">PREVIOUS ANSWER: DEFICIENT (CORRECT OPTION: {correct_opt})</span>'
                    f'<div style="font-size: 0.9rem; color: #141413; margin-top: 2px;">{clean_expl}</div>'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

    # Cadence Clock
    time_limit = st.session_state.get("mcq_time_limit", 45)
    elapsed = time.time() - (st.session_state.mcq_question_start or time.time())
    remaining = max(0, time_limit - elapsed) if time_limit > 0 else 0

    if time_limit > 0:
        timer_urgency = "var(--accent-red)" if remaining < 10 else "var(--ink-charcoal)"
        pct_left = max(0.0, min(100.0, (remaining / time_limit) * 100))
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.65rem 1rem; border-radius: 4px; margin-top: 0.8rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <span style="font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.06em; color: var(--ink-tertiary);">CADENCE CLOCK</span>
                    <span style="font-family: var(--font-mono); font-size: 0.95rem; font-weight: 700; color: {timer_urgency};">
                        {int(remaining):02d}s REMAINING ({time_limit}s TARGET)
                    </span>
                </div>
                <div style="width: 100%; height: 4px; background: #EDE8DE; border-radius: 2px; overflow: hidden;">
                    <div style="width: {pct_left}%; height: 100%; background: {timer_urgency}; transition: width 0.3s ease;"></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.5rem 1rem; border-radius: 4px; margin-top: 0.8rem; font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">
                MODE: UNTIMED PRACTICE // TAKE YOUR TIME TO DECONSTRUCT THE PROBLEM
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Question Docket Header & Content via shared safe helper
    topic = current_q.get("topic", "Computer Science")
    difficulty = current_q.get("difficulty", "medium")
    interview_round = current_q.get("interview_round", "")

    extra_badges = []
    if interview_round:
        extra_badges.append(f"ROUND: {interview_round}")

    render_question_card(
        question_text=current_q.get("question_text", ""),
        topic=topic,
        extra_badges=extra_badges,
        right_meta=f"COMPLEXITY: {difficulty}",
    )

    # Normalize options cleanly
    raw_options = current_q.get("options", [])
    display_options, letter_map = _normalize_options(raw_options)

    # Use st.form to isolate radio selection and prevent unwanted full-page reruns
    with st.form(key=f"mcq_form_{current_idx}", clear_on_submit=False):
        st.markdown(
            '<div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary); letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 0.4rem;">SELECT CANDIDATE HYPOTHESIS:</div>',
            unsafe_allow_html=True,
        )
        selected_option = st.radio(
            label="Candidate Hypothesis Selection",
            options=display_options,
            key=f"mcq_radio_{current_idx}",
            index=None,
            label_visibility="collapsed",
        )

        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
        col_btn1, col_btn2 = st.columns([3, 1], gap="medium")
        with col_btn1:
            submitted = st.form_submit_button(
                "CONFIRM SELECTION →",
                type="primary",
                use_container_width=True,
            )
        with col_btn2:
            st.form_submit_button(
                "LOCK IN",
                type="secondary",
                use_container_width=True,
                help="Confirm and advance to the next item.",
            )

    if submitted:
        if selected_option is None:
            st.warning("⚠️ Please select an option prior to confirming your submission.")
        else:
            answer_letter = letter_map.get(selected_option, selected_option[0].upper())
            response_time = time.time() - (st.session_state.mcq_question_start or time.time())
            _submit_mcq_answer(session, current_q, answer_letter, False, response_time, api_base, headers)

    # Aux controls: Skip and End Early
    col_aux1, col_aux2 = st.columns([1, 1], gap="medium")
    with col_aux1:
        if st.button("⏭️ PASS / SKIP QUESTION", key=f"skip_btn_{current_idx}", use_container_width=True, type="secondary"):
            response_time = time.time() - (st.session_state.mcq_question_start or time.time())
            _submit_mcq_answer(session, current_q, "", True, response_time, api_base, headers)
    with col_aux2:
        if st.button("⏹️ TERMINATE EXAMINATION PREMATURELY", key="end_mcq_early", use_container_width=True, type="secondary"):
            st.session_state.mcq_current_question = None
            st.rerun()


def _submit_mcq_answer(session, current_q, answer_letter, is_timeout, response_time, api_base, headers):
    """Submit MCQ answer to backend API."""
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
                "topic": current_q.get("topic", "General"),
            })
            # Keep feedback persistent across questions
            st.session_state.mcq_last_feedback = result

            if result["is_complete"]:
                st.session_state.mcq_current_question = None
            else:
                st.session_state.mcq_current_question = result.get("next_question")
                st.session_state.mcq_question_start = time.time()
            st.rerun()
        else:
            detail = resp.json().get("detail", "Submission failed")
            st.error(f"❌ {detail}")
    except Exception as e:
        st.error(f"Error submitting answer: {str(e)}")


def _render_mcq_completion(session: dict, api_base: str, headers: dict):
    """Render the assessment completion report."""
    scores = st.session_state.mcq_scores
    total = len(scores)
    correct = sum(1 for s in scores if s.get("is_correct"))
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

    # Topic Breakdown
    st.markdown("---")
    st.markdown("### Topic-Level Breakdown")
    topic_stats = {}
    for s in scores:
        t = s.get("topic", "General")
        if t not in topic_stats:
            topic_stats[t] = {"correct": 0, "total": 0}
        topic_stats[t]["total"] += 1
        if s.get("is_correct"):
            topic_stats[t]["correct"] += 1

    for topic_name, stats in topic_stats.items():
        pct = round(stats["correct"] / stats["total"] * 100, 1)
        badge_style = "background: rgba(45, 90, 39, 0.1); color: #2D5A27;" if pct >= 70 else "background: rgba(217, 56, 30, 0.1); color: var(--accent-red);"
        st.markdown(
            f"""
            <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.7rem 1.1rem; border-radius: 4px; margin-bottom: 0.5rem;">
                <span style="font-family: var(--font-sans); font-weight: 600; color: var(--ink-charcoal);">{html.escape(topic_name)}</span>
                <span style="font-family: var(--font-mono); font-size: 0.8rem; padding: 2px 8px; border-radius: 3px; {badge_style}">
                    {stats['correct']}/{stats['total']} ({pct}%)
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Detailed Question Telemetry
    st.markdown("---")
    with st.expander("INSPECT DETAILED QUESTION TELEMETRY", expanded=False):
        for i, s in enumerate(scores, 1):
            is_corr = s.get("is_correct", False)
            status_text = "CORRECT" if is_corr else "INCORRECT"
            color = "#2D5A27" if is_corr else "var(--accent-red)"
            st.markdown(
                f"""
                <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 0.6rem;">
                    <div style="display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 0.72rem;">
                        <span style="color: var(--ink-charcoal); font-weight: 600;">ITEM #{i} — {html.escape(s.get('topic', 'General'))}</span>
                        <span style="color: {color}; font-weight: 700;">{status_text} (BENCHMARK: {s.get('correct_answer', '')})</span>
                    </div>
                    <div style="font-size: 0.88rem; color: var(--ink-muted); margin-top: 4px;">{html.escape(s.get('explanation', ''))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    col_a, col_b = st.columns(2, gap="medium")
    with col_a:
        if st.button("PROCEED TO ANALYTICAL DASHBOARD →", use_container_width=True, type="primary", key="mcq_goto_dashboard"):
            st.session_state.current_page = "dashboard"
            st.rerun()
    with col_b:
        if st.button("INITIALIZE FRESH SESSION", use_container_width=True, type="secondary", key="mcq_fresh_session"):
            st.session_state.mcq_session = None
            st.session_state.mcq_current_question = None
            st.session_state.mcq_scores = []
            st.session_state.mcq_last_feedback = None
            st.rerun()

