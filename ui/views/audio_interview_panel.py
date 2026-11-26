"""
Adaptive AI Audio Interview Panel (BeFluent-Inspired)
======================================================
Provides the complete conversational audio interview experience:
- Configuration calibrated to dossier role/organization, Question Bank integration & custom scoring weights
- Browser TTS question playback (Web Speech API)
- Browser microphone recording (st.audio_input) + audio file upload fallback
- Whisper STT transcription review/retry with confidence & fluency metrics
- Adaptive follow-ups & stateful session resumption
- Rich Plotly performance report & historical progress tracking
"""

import html
import time
from datetime import datetime

import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components

from ui.theme import render_empty_state, render_question_card


def _render_tts_button(question_text: str, key_suffix: str):
    """Render a browser Web Speech API Text-to-Speech button for listening to the question."""
    safe_js_text = (
        question_text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("</", "<\\/")
    )
    components.html(
        f"""
        <div style="display:flex; align-items:center; gap:10px; font-family:'JetBrains Mono', monospace;">
            <button id="tts-play-{key_suffix}" onclick="speakQ_{key_suffix}()"
                style="background:#141413; color:#F5F2EC; border:none; border-radius:4px; padding:6px 12px; cursor:pointer; font-size:12px; letter-spacing:0.04em;">
                🔊 LISTEN TO QUESTION
            </button>
            <button onclick="stopQ_{key_suffix}()"
                style="background:#FFFFFF; color:#141413; border:1px solid #D8D1C5; border-radius:4px; padding:6px 10px; cursor:pointer; font-size:12px;">
                ⏹ STOP
            </button>
            <span id="tts-status-{key_suffix}" style="font-size:11px; color:#8A8780;"></span>
        </div>
        <script>
            function speakQ_{key_suffix}() {{
                if (!('speechSynthesis' in window)) {{
                    document.getElementById('tts-status-{key_suffix}').textContent = 'TTS not supported in this browser.';
                    return;
                }}
                window.speechSynthesis.cancel();
                const utter = new SpeechSynthesisUtterance("{safe_js_text}");
                utter.rate = 0.98;
                utter.pitch = 1.0;
                utter.onstart = () => {{ document.getElementById('tts-status-{key_suffix}').textContent = 'Speaking...'; }};
                utter.onend = () => {{ document.getElementById('tts-status-{key_suffix}').textContent = ''; }};
                window.speechSynthesis.speak(utter);
            }}
            function stopQ_{key_suffix}() {{
                if ('speechSynthesis' in window) window.speechSynthesis.cancel();
                document.getElementById('tts-status-{key_suffix}').textContent = '';
            }}
        </script>
        """,
        height=44,
    )


def render_audio_interview_mode(api_base: str, headers: dict):
    """Main entry point for the Adaptive AI Audio Interview tab."""
    if "audio_session_id" not in st.session_state:
        st.session_state.audio_session_id = None
    if "audio_session_state" not in st.session_state:
        st.session_state.audio_session_state = None
    if "audio_pending_stt" not in st.session_state:
        st.session_state.audio_pending_stt = None
    if "audio_last_turn_feedback" not in st.session_state:
        st.session_state.audio_last_turn_feedback = None
    if "audio_report" not in st.session_state:
        st.session_state.audio_report = None

    # If a completed report is active, show report
    if st.session_state.audio_report is not None:
        render_audio_report(st.session_state.audio_report, api_base, headers)
        return

    # If no active session, show setup + history
    if st.session_state.audio_session_id is None:
        _render_audio_setup(api_base, headers)
        return

    # Active session UI
    _render_active_audio_interview(api_base, headers)


def _render_audio_setup(api_base: str, headers: dict):
    """Render setup form, active session resume, and past audio interview history."""
    # Check history for active/resumable or completed sessions
    history = []
    try:
        h_resp = requests.get(f"{api_base}/api/v1/audio-interview/history", headers=headers, timeout=8)
        if h_resp.status_code == 200:
            history = h_resp.json().get("sessions", [])
    except requests.ConnectionError:
        st.error("❌ Backend server unreachable at http://127.0.0.1:8000.")
        return
    except Exception:
        pass

    active_sessions = [s for s in history if s.get("status") == "active"]
    if active_sessions:
        latest_active = active_sessions[0]
        sid = latest_active["session_id"]
        round_lbl = latest_active.get("interview_round", "Technical").upper()
        comp_badge = f" @ {html.escape(latest_active['company'])}" if latest_active.get("company") else ""
        st.markdown(
            f"""
<div style="background: rgba(26, 115, 232, 0.06); border: 1px solid #1a73e8; border-radius: 6px; padding: 1rem 1.25rem; margin-bottom: 1rem;">
<span class="editorial-tag" style="background: rgba(26, 115, 232, 0.12); color: #1a73e8;">ACTIVE AUDIO INTERVIEW FOUND</span>
<div style="font-weight:600; margin-top:4px;">{html.escape(latest_active['job_role'])}{comp_badge} ({round_lbl})</div>
</div>
""",
            unsafe_allow_html=True,
        )
        if st.button("RESUME AUDIO INTERVIEW →", key=f"resume_aud_{sid}", type="primary"):
            _load_and_resume_audio(sid, api_base, headers)
            return

    # Check user dossier (Resume + Job Description uploaded on Page 01)
    dossier_role = st.session_state.get("dossier_role", "")
    dossier_company = st.session_state.get("dossier_company", "")
    resume_ok = False
    jd_ok = False
    try:
        doc_resp = requests.get(f"{api_base}/api/v1/upload/documents", headers=headers, timeout=8)
        if doc_resp.status_code == 200:
            ddata = doc_resp.json()
            resume_ok = ddata.get("resume", {}).get("uploaded", False)
            jd_info = ddata.get("jd", {})
            jd_ok = jd_info.get("uploaded", False)
            if jd_ok:
                dossier_role = ddata.get("dossier_role") or jd_info.get("parsed_role") or dossier_role or "Software Engineer"
                dossier_company = ddata.get("dossier_company") or jd_info.get("parsed_company") or dossier_company
                st.session_state["dossier_role"] = dossier_role
                st.session_state["dossier_company"] = dossier_company
    except Exception:
        pass

    if not resume_ok or not jd_ok:
        render_empty_state(
            title="Dossier Required Before Audio Interview",
            message="Please upload your Resume and Target Job Description on '01 — Upload Dossier' first so we can calibrate your interview role, organization, and skill topics automatically.",
            meta_code="GATEWAY // DOSSIER MISSING",
        )
        if st.button("GO TO 01 — UPLOAD DOSSIER →", type="primary", use_container_width=True, key="aud_goto_upload"):
            st.session_state.current_page = "upload"
            st.rerun()
        return

    prefill_question = st.session_state.pop("audio_prefill_question", "")
    prefill_topic = st.session_state.pop("audio_prefill_topic", "")

    if prefill_question:
        st.info(f"🎯 **Selected Practice Question from Bank**: *{prefill_question}*")

    target_line = f"{dossier_role} @ {dossier_company}" if dossier_company else dossier_role

    st.markdown(
        f"""
<div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.5rem; border-radius: 6px; margin: 0.75rem 0 1rem 0;">
<div style="display:flex; justify-content:space-between; align-items:baseline;">
<span class="editorial-tag">BEFLUENT SPEECH ENGINE // ADAPTIVE AI</span>
<span style="font-family:var(--font-mono); font-size:0.72rem; color:var(--ink-tertiary);">GROQ WHISPER + LLAMA ORCHESTRATOR</span>
</div>
<h3 style="margin: 0.5rem 0 0.25rem 0;">Configure Conversational Audio Interview</h3>
<p style="font-size: 0.9rem; color: var(--ink-charcoal); font-weight: 600; margin: 0.35rem 0 0.25rem 0;">
Interviewing for: {html.escape(target_line)} (from your dossier)
</p>
<p style="font-size: 0.88rem; color: var(--ink-muted); margin:0;">
Speak your answers naturally via microphone. The AI interviewer transcribes your speech, identifies conceptual gaps, dynamically asks targeted follow-ups, adapts difficulty, and produces a 100-mark diagnostic report.
</p>
</div>
""",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2, gap="medium")
    with col1:
        interview_round = st.selectbox(
            "Interview Round",
            options=["Technical", "HR / Behavioral", "System Design", "Managerial"],
            index=0,
            key="aud_round",
        )
        difficulty = st.selectbox("Difficulty Level", ["easy", "medium", "hard"], index=1, key="aud_diff")

    with col2:
        c_lim1, c_lim2 = st.columns(2)
        with c_lim1:
            max_questions = st.slider("Main Questions", min_value=2, max_value=12, value=5, key="aud_max_q")
        with c_lim2:
            max_duration = st.slider("Max Minutes", min_value=5, max_value=60, value=20, key="aud_max_dur")

    show_live_fb = st.checkbox(
        "Show live marks & conceptual feedback after each answer (uncheck for realistic silent interviewer mode)",
        value=True,
        key="aud_show_live_fb",
    )
    st.session_state["audio_show_live_feedback"] = show_live_fb

    is_tech_round = interview_round in ("Technical", "System Design")
    with st.expander("⚙️ Configure Scoring Rubric Weights (Optional — Total normalized to 100)", expanded=False):
        wc1, wc2, wc3 = st.columns(3)
        with wc1:
            w_tech = st.number_input("Technical Correctness", 0, 100, 30 if is_tech_round else 10, key="w_tech")
            w_conc = st.number_input("Conceptual Understanding", 0, 100, 20 if is_tech_round else 15, key="w_conc")
        with wc2:
            w_rel = st.number_input("Relevance", 0, 100, 15 if is_tech_round else 25, key="w_rel")
            w_comp = st.number_input("Completeness", 0, 100, 15, key="w_comp")
        with wc3:
            w_clar = st.number_input("Clarity", 0, 100, 10 if is_tech_round else 15, key="w_clar")
            w_comm = st.number_input("Communication", 0, 100, 10 if is_tech_round else 20, key="w_comm")
        custom_weights = {
            "technical_correctness": int(w_tech),
            "conceptual_understanding": int(w_conc),
            "relevance": int(w_rel),
            "completeness": int(w_comp),
            "clarity": int(w_clar),
            "communication": int(w_comm),
        }

    if st.button("🎙️ START ADAPTIVE AUDIO INTERVIEW →", type="primary", use_container_width=True, key="start_aud_btn"):
        with st.spinner("Preparing interviewer context & selecting questions from Question Bank..."):
            try:
                payload = {
                    "interview_round": interview_round,
                    "difficulty": difficulty,
                    "max_questions": max_questions,
                    "max_duration_minutes": max_duration,
                    "custom_weights": custom_weights,
                    "initial_question": prefill_question,
                    "initial_topic": prefill_topic,
                }
                resp = requests.post(
                    f"{api_base}/api/v1/audio-interview/start",
                    json=payload,
                    headers=headers,
                    timeout=45,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.audio_session_id = data["session_id"]
                    st.session_state.audio_session_state = data
                    st.session_state.audio_pending_stt = None
                    st.session_state.audio_last_turn_feedback = None
                    st.session_state.audio_report = None
                    st.rerun()
                else:
                    st.error(f"❌ {resp.json().get('detail', 'Could not start audio interview')}")
            except Exception as e:
                st.error(f"Error starting interview: {e}")

    # Past Audio Interview Reports
    completed = [s for s in history if s.get("status") == "completed"]
    if completed:
        st.markdown("---")
        st.markdown("### 📜 Past Audio Interview Reports")
        for s in completed[:8]:
            dt_str = datetime.fromtimestamp(s["started_at"]).strftime("%Y-%m-%d %H:%M")
            comp_str = f" @ {s['company']}" if s.get("company") else ""
            score_str = f"{s['overall_score']:.1f}/100" if s.get("overall_score") is not None else "N/A"
            round_str = s.get("interview_round", "Technical").upper()
            c_h1, c_h2 = st.columns([4, 1])
            with c_h1:
                st.markdown(
                    f"**{html.escape(s['job_role'])}{html.escape(comp_str)}** ({round_str}) — "
                    f"Score: `{score_str}` • {dt_str}"
                )
            with c_h2:
                if st.button("OPEN REPORT", key=f"open_rep_{s['session_id']}", use_container_width=True, type="secondary"):
                    r_resp = requests.get(f"{api_base}/api/v1/audio-interview/{s['session_id']}/report", headers=headers, timeout=15)
                    if r_resp.status_code == 200:
                        st.session_state.audio_report = r_resp.json()
                        st.rerun()


def _load_and_resume_audio(session_id: str, api_base: str, headers: dict):
    """Fetch active audio session state from backend and resume."""
    try:
        resp = requests.get(f"{api_base}/api/v1/audio-interview/{session_id}", headers=headers, timeout=15)
        if resp.status_code == 200:
            payload = resp.json()
            sess = payload["session"]
            st.session_state.audio_session_id = session_id
            st.session_state.audio_session_state = {
                "session_id": session_id,
                "company": sess["company"],
                "job_role": sess["job_role"],
                "interview_round": sess["interview_round"],
                "difficulty": sess["difficulty"],
                "max_questions": sess["max_questions"],
                "max_duration_minutes": sess["max_duration_minutes"],
                "scoring_weights": sess["scoring_weights"],
                "current_question": sess["current_question"],
                "turn_index": sess["current_question_index"],
                "main_question_number": sess["state"].get("main_questions_asked", 1),
                "is_followup": sess["followups_on_current"] > 0,
            }
            st.session_state.audio_pending_stt = None
            st.session_state.audio_report = None
            st.rerun()
    except Exception as e:
        st.error(f"Failed to resume audio interview: {e}")


def _render_active_audio_interview(api_base: str, headers: dict):
    """Render the live adaptive conversational audio interview loop."""
    sess = st.session_state.audio_session_state
    session_id = st.session_state.audio_session_id
    current_q = sess["current_question"]
    turn_idx = sess.get("turn_index", 0)
    main_num = sess.get("main_question_number", 1)
    max_q = sess.get("max_questions", 5)
    is_followup = sess.get("is_followup", False)

    # Progress & Telemetry strip
    t_c1, t_c2, t_c3 = st.columns([2, 1, 1], gap="medium")
    with t_c1:
        st.markdown(
            f"""
            <div style="background:var(--bg-card); border:1px solid var(--border-subtle); padding:0.7rem 1rem; border-radius:4px;">
                <div style="font-family:var(--font-mono); font-size:0.68rem; color:var(--ink-tertiary);">INTERVIEW PROGRESS</div>
                <div style="font-family:var(--font-serif); font-size:1.55rem; color:var(--ink-charcoal);">
                    MAIN QUESTION {main_num} OF {max_q}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with t_c2:
        mode_lbl = "ADAPTIVE FOLLOW-UP" if is_followup else "PRIMARY QUESTION"
        mode_clr = "#D9381E" if is_followup else "#2D5A27"
        st.markdown(
            f"""
            <div style="background:var(--bg-card); border:1px solid var(--border-subtle); padding:0.7rem 1rem; border-radius:4px;">
                <div style="font-family:var(--font-mono); font-size:0.68rem; color:var(--ink-tertiary);">TURN TYPE</div>
                <div style="font-family:var(--font-mono); font-size:0.95rem; font-weight:700; color:{mode_clr}; margin-top:4px;">{mode_lbl}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with t_c3:
        st.markdown(
            f"""
            <div style="background:var(--bg-card); border:1px solid var(--border-subtle); padding:0.7rem 1rem; border-radius:4px;">
                <div style="font-family:var(--font-mono); font-size:0.68rem; color:var(--ink-tertiary);">ROLE / COMPANY</div>
                <div style="font-family:var(--font-sans); font-size:0.88rem; font-weight:600; color:var(--ink-charcoal); margin-top:4px;">
                    {html.escape(sess.get('job_role', ''))} {f"@ {html.escape(sess['company'].title())}" if sess.get('company') else ''}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.progress(min(1.0, main_num / max(max_q, 1)))

    # Optional previous turn adaptive feedback
    if st.session_state.audio_last_turn_feedback and st.session_state.get("audio_show_live_feedback", True):
        prev = st.session_state.audio_last_turn_feedback
        ev = prev.get("evaluation", {})
        sc = ev.get("evaluation", {}).get("score", 0)
        reason = prev.get("reason_for_next_question", "")
        st.markdown(
            f"""
            <div style="background: rgba(26,115,232,0.06); border:1px solid #1a73e8; border-radius:4px; padding:0.8rem 1rem; margin:0.6rem 0;">
                <div style="font-family:var(--font-mono); font-size:0.72rem; color:#1a73e8; font-weight:700;">
                    PREVIOUS RESPONSE EVALUATED: {sc}/100 ({ev.get('answer_category', '').upper()}) • NEXT ACTION: {prev.get('next_action')}
                </div>
                <div style="font-size:0.88rem; color:var(--ink-charcoal); margin-top:4px;">{html.escape(ev.get('feedback', ''))}</div>
                {f"<div style='font-size:0.8rem; color:var(--ink-muted); margin-top:4px;'><em>Interviewer Adaptation: {html.escape(reason)}</em></div>" if reason else ""}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Current Question Card via shared safe helper
    q_text = current_q.get("question_text", "")
    q_topic = current_q.get("topic", "General")
    q_diff = current_q.get("difficulty", "medium")
    q_src = current_q.get("source", "question_bank")

    render_question_card(
        question_text=q_text,
        topic=q_topic,
        extra_badges=[f"SOURCE: {q_src}"],
        right_meta=f"DIFFICULTY: {q_diff}",
    )

    # Listen to Question (Web Speech TTS)
    _render_tts_button(q_text, key_suffix=f"t{turn_idx}")

    # Step A: Record or Upload Audio if not yet transcribed for this turn
    if st.session_state.audio_pending_stt is None:
        rec_tab, up_tab = st.tabs(["🎙️ Record with Microphone", "📁 Upload Audio File"])

        with rec_tab:
            st.caption("Click the microphone below to start recording. Stop when finished to replay or transcribe.")
            recorded_audio = st.audio_input("Speak your answer", sample_rate=16000, key=f"mic_rec_{turn_idx}")
            if recorded_audio is not None:
                if st.button("🔊 TRANSCRIBE RECORDED ANSWER →", type="primary", use_container_width=True, key=f"tr_rec_{turn_idx}"):
                    _transcribe_uploaded_bytes(
                        session_id, "recorded_answer.wav", recorded_audio.getvalue(), "audio/wav", api_base, headers
                    )

        with up_tab:
            up_file = st.file_uploader(
                "Upload audio answer (.wav, .mp3, .m4a, .webm, .ogg)",
                type=["wav", "mp3", "m4a", "webm", "ogg"],
                key=f"aud_up_{turn_idx}",
            )
            if up_file is not None:
                st.audio(up_file)
                if st.button("🔊 TRANSCRIBE UPLOADED AUDIO →", type="primary", use_container_width=True, key=f"tr_up_{turn_idx}"):
                    _transcribe_uploaded_bytes(
                        session_id, up_file.name, up_file.getvalue(), up_file.type or "audio/wav", api_base, headers
                    )

    # Step B: Review Transcript & Submit for Adaptive Evaluation
    else:
        stt = st.session_state.audio_pending_stt
        if stt.get("noise_warning"):
            st.warning(f"⚠️ {stt['noise_warning']}")

        flu = stt.get("fluency_metrics", {})
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Duration", f"{stt.get('duration_seconds', 0):.1f}s")
        m2.metric("Speaking Pace", f"{flu.get('words_per_minute', 0)} WPM")
        m3.metric("STT Confidence", f"{round(stt.get('confidence', 0) * 100)}%")
        m4.metric("Filler Words", f"{flu.get('filler_word_count', 0)}")

        edited_transcript = st.text_area(
            "Review Transcript (you may correct minor speech-recognition typos before submitting)",
            value=stt.get("transcript", ""),
            height=130,
            key=f"rev_tr_{turn_idx}",
        )

        col_s1, col_s2 = st.columns([3, 1], gap="medium")
        with col_s1:
            if st.button("SUBMIT ANSWER & CONTINUE INTERVIEW →", type="primary", use_container_width=True, key=f"sub_turn_{turn_idx}"):
                if not edited_transcript.strip():
                    st.error("Transcript is empty. Please re-record your answer.")
                else:
                    with st.spinner("Evaluating response & determining adaptive next question..."):
                        try:
                            resp = requests.post(
                                f"{api_base}/api/v1/audio-interview/{session_id}/submit-turn",
                                json={
                                    "transcript": edited_transcript.strip(),
                                    "audio_duration": stt.get("duration_seconds", 0.0),
                                    "stt_confidence": stt.get("confidence", 1.0),
                                    "fluency_metrics": flu,
                                    "audio_path": stt.get("audio_path", ""),
                                },
                                headers=headers,
                                timeout=60,
                            )
                            if resp.status_code == 200:
                                res = resp.json()
                                st.session_state.audio_pending_stt = None
                                st.session_state.audio_last_turn_feedback = res
                                if res.get("is_complete"):
                                    st.session_state.audio_report = res.get("report")
                                    st.session_state.audio_session_id = None
                                    st.session_state.audio_session_state = None
                                else:
                                    sess["current_question"] = res["next_question"]
                                    sess["turn_index"] = turn_idx + 1
                                    sess["main_question_number"] = res.get("main_question_number", main_num)
                                    sess["is_followup"] = res.get("is_followup", False)
                                st.rerun()
                            else:
                                st.error(f"❌ {resp.json().get('detail', 'Evaluation failed')}")
                        except Exception as e:
                            st.error(f"Submission error: {e}")
        with col_s2:
            if st.button("🔄 RETRY RECORDING", type="secondary", use_container_width=True, key=f"retry_rec_{turn_idx}"):
                st.session_state.audio_pending_stt = None
                st.rerun()

    st.markdown("<div style='margin-top:1.2rem;'></div>", unsafe_allow_html=True)
    if st.button("⏹ FINISH INTERVIEW & GENERATE REPORT", key="finish_aud_early", type="secondary"):
        with st.spinner("Generating comprehensive interview performance report..."):
            try:
                e_resp = requests.post(f"{api_base}/api/v1/audio-interview/{session_id}/end", headers=headers, timeout=30)
                if e_resp.status_code == 200:
                    st.session_state.audio_report = e_resp.json().get("report")
                    st.session_state.audio_session_id = None
                    st.session_state.audio_session_state = None
                    st.session_state.audio_pending_stt = None
                    st.rerun()
            except Exception as e:
                st.error(f"Error ending interview: {e}")


def _transcribe_uploaded_bytes(session_id: str, filename: str, raw_bytes: bytes, mime: str, api_base: str, headers: dict):
    """Send audio bytes to Whisper STT backend and store result in session_state."""
    with st.spinner("Transcribing audio with Groq Whisper (whisper-large-v3-turbo)..."):
        try:
            resp = requests.post(
                f"{api_base}/api/v1/audio-interview/{session_id}/transcribe",
                files={"file": (filename, raw_bytes, mime)},
                headers=headers,
                timeout=60,
            )
            if resp.status_code == 200:
                st.session_state.audio_pending_stt = resp.json()
                st.rerun()
            else:
                st.error(f"❌ {resp.json().get('detail', 'Transcription failed')}")
        except Exception as e:
            st.error(f"Upload/Transcription error: {e}")


def render_audio_report(report: dict, api_base: str, headers: dict):
    """Render the full Performance Report with Plotly visualizations & turn-by-turn inspection."""
    st.markdown(
        f"""
        <div class="editorial-header-banner" style="margin-top: 0.5rem;">
            <div>
                <span class="editorial-tag" style="background:rgba(45,90,39,0.1); color:#2D5A27;">FINAL DIAGNOSTIC REPORT</span>
                <h1 style="margin:0.3rem 0 0 0;">Audio Interview Performance</h1>
            </div>
            <div style="font-family:var(--font-mono); font-size:0.75rem; color:var(--ink-tertiary); text-align:right;">
                {html.escape(report.get('job_role', '').upper())}<br>
                {html.escape(report.get('company', 'GENERAL').upper() or 'GENERAL')} • {html.escape(report.get('interview_round', 'Technical').upper())}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Top KPI cards
    c1, c2, c3, c4 = st.columns(4, gap="medium")
    c1.metric("Overall Score", f"{report.get('overall_score', 0):.1f} / 100")
    c2.metric("Total Turns", f"{report.get('total_questions_asked', 0)} ({report.get('followup_questions_count', 0)} follow-ups)")
    c3.metric("Technical Knowledge", f"{report.get('technical_knowledge_score', 0):.0f}%")
    c4.metric("Communication", f"{report.get('communication_score', 0):.0f}%")

    # Visualizations
    dim_pcts = report.get("dimension_percentages", {})
    turns = report.get("turns", [])

    col_v1, col_v2 = st.columns(2, gap="large")
    with col_v1:
        if dim_pcts:
            labels = [k.replace("_", " ").title() for k in dim_pcts.keys()]
            vals = list(dim_pcts.values())
            fig_dim = go.Figure(go.Bar(
                x=vals, y=labels, orientation="h",
                marker_color=["#2D5A27" if v >= 70 else "#D9381E" for v in vals],
                text=[f"{v:.0f}%" for v in vals],
                textposition="auto",
            ))
            fig_dim.update_layout(
                title="Rubric Performance (%)",
                xaxis=dict(range=[0, 100], gridcolor="#EFEBE3"),
                paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                height=340, margin=dict(l=20, r=20, t=45, b=20),
            )
            st.plotly_chart(fig_dim, use_container_width=True)

    with col_v2:
        if turns:
            q_labels = [f"Q{t['turn_index'] + 1}{'*' if t['is_followup'] else ''}" for t in turns]
            q_scores = [t["score"] for t in turns]
            fig_q = go.Figure(go.Scatter(
                x=q_labels, y=q_scores, mode="lines+markers+text",
                text=[f"{s:.0f}" for s in q_scores], textposition="top center",
                line=dict(color="#141413", width=2.5),
                marker=dict(size=9, color="#D9381E"),
            ))
            fig_q.update_layout(
                title="Question-wise Marks Trajectory (* = Follow-up)",
                yaxis=dict(range=[0, 105], gridcolor="#EFEBE3"),
                paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                height=340, margin=dict(l=20, r=20, t=45, b=20),
            )
            st.plotly_chart(fig_q, use_container_width=True)

    # Historical Progress Chart
    try:
        h_resp = requests.get(f"{api_base}/api/v1/audio-interview/history", headers=headers, timeout=8)
        if h_resp.status_code == 200:
            comp_hist = [s for s in h_resp.json().get("sessions", []) if s.get("status") == "completed" and s.get("overall_score") is not None]
            if len(comp_hist) >= 2:
                comp_hist.reverse()
                fig_hist = go.Figure(go.Scatter(
                    x=[datetime.fromtimestamp(s["started_at"]).strftime("%b %d %H:%M") for s in comp_hist],
                    y=[s["overall_score"] for s in comp_hist],
                    mode="lines+markers",
                    line=dict(color="#2D5A27", width=2.5),
                ))
                fig_hist.update_layout(
                    title="Historical Audio Interview Progress",
                    yaxis=dict(range=[0, 100], gridcolor="#EFEBE3"),
                    paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                    height=260, margin=dict(l=20, r=20, t=40, b=20),
                )
                st.plotly_chart(fig_hist, use_container_width=True)
    except Exception:
        pass

    # Qualitative Breakdown
    st.markdown("---")
    qc1, qc2 = st.columns(2, gap="medium")
    with qc1:
        st.markdown("#### ✅ Strengths")
        for s in report.get("strengths", []) or ["Completed the interview session."]:
            st.markdown(f"- {s}")
        st.markdown("#### ⚠️ Areas Requiring Improvement")
        for w in report.get("weaknesses", []) or ["No major weaknesses flagged."]:
            st.markdown(f"- {w}")
    with qc2:
        st.markdown("#### ❌ Incorrect / Misunderstood Concepts")
        for ic in report.get("incorrect_concepts", []) or ["None flagged."]:
            st.markdown(f"- {ic}")
        st.markdown("#### 🔍 Missing Concepts")
        for mc in report.get("missing_concepts", []) or ["None flagged."]:
            st.markdown(f"- {mc}")

    # Revision Plan & Practice Questions
    st.markdown("---")
    st.markdown("### 📚 Actionable Improvement Plan & Revision")
    for step in report.get("action_plan", []):
        st.markdown(f"- {step}")

    if report.get("recommended_revision_topics"):
        st.markdown("**Recommended Revision Topics:** " + ", ".join(f"`{t}`" for t in report["recommended_revision_topics"]))

    if report.get("revision_notes"):
        with st.expander("📖 Matched Excerpts from Course Notes", expanded=False):
            for note in report["revision_notes"]:
                st.markdown(f"**{note['topic']}** (*{note['source_file']}*): {note['excerpt']}")

    if report.get("personalized_practice_questions"):
        with st.expander("🎯 Personalized Practice Questions", expanded=False):
            for pq in report["personalized_practice_questions"]:
                st.markdown(f"- **[{pq['topic']} | {pq['difficulty'].upper()}]** {pq['question_text']}")

    # Turn-by-Turn Inspection
    st.markdown("---")
    st.markdown("### 🎙️ Question-by-Question Detailed Review")
    sid = report.get("session_id", "")
    for t in turns:
        t_idx = t["turn_index"]
        tag = "FOLLOW-UP" if t["is_followup"] else "MAIN"
        with st.expander(f"[{tag}] Q{t_idx + 1}: {t['question_text'][:85]}... — Score: {t['score']}/100", expanded=False):
            st.markdown(f"**Question:** {t['question_text']}")
            st.markdown(f"**Transcript:** {t['transcript']}")
            flu = t.get("fluency_metrics", {})
            st.caption(
                f"Duration: {t.get('audio_duration', 0):.1f}s | "
                f"Pace: {flu.get('words_per_minute', 0)} WPM | "
                f"Fillers: {flu.get('filler_word_count', 0)} | "
                f"STT Confidence: {round(t.get('stt_confidence', 1)*100)}%"
            )

            # Retained Audio Replay
            if t.get("audio_path") and sid:
                try:
                    a_resp = requests.get(f"{api_base}/api/v1/audio-interview/{sid}/audio/{t_idx}", headers=headers, timeout=10)
                    if a_resp.status_code == 200:
                        st.audio(a_resp.content)
                except Exception:
                    pass

            ev = t.get("evaluation", {})
            st.markdown(f"**Feedback:** {ev.get('feedback', '')}")
            if ev.get("communication_feedback"):
                st.markdown(f"**Communication Feedback:** {ev['communication_feedback']}")
            scores_dict = ev.get("evaluation", {})
            if scores_dict:
                st.json(scores_dict)

    st.markdown("---")
    c_b1, c_b2 = st.columns(2)
    with c_b1:
        if st.button("← START ANOTHER AUDIO INTERVIEW", type="primary", use_container_width=True, key="aud_rep_again"):
            st.session_state.audio_report = None
            st.rerun()
    with c_b2:
        if st.button("OPEN FULL ANALYTICS DASHBOARD →", type="secondary", use_container_width=True, key="aud_rep_dash"):
            st.session_state.audio_report = None
            st.session_state.current_page = "dashboard"
            st.rerun()
