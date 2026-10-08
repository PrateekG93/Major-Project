"""
Performance Dashboard View (Diagnostic Analytics Journal)
==========================================================
Editorial analytics publication:
- High-contrast Plotly telemetry tailored to bone (#F5F2EC) and charcoal (#141413) palette
- ATS Compatibility index with section and action-verb metrics
- Structured remediation study plan with priority badges and textbook reading timeframes
"""

import requests
import streamlit as st
import plotly.graph_objects as go
from ui.theme import render_editorial_title, render_empty_state


def render():
    render_editorial_title(
        title="Diagnostic Analytics Journal",
        subtitle="Quantitative assessment telemetry: MCQ domain proficiency, ATS screening compatibility, and adaptive study remediation.",
        meta_tag="MODULE 04 // DIAGNOSTICS",
    )

    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")
    token = st.session_state.get("session_token", "")
    headers = {"x-session-token": token}

    tab1, tab2, tab3 = st.tabs([
        "01 — MCQ Domain Proficiency",
        "02 — ATS Resume Audit",
        "03 — Remediation Study Plan",
    ])

    with tab1:
        _render_mcq_performance(api_base, headers)

    with tab2:
        _render_ats_analysis(api_base, headers)

    with tab3:
        _render_study_plan(api_base, headers)


def _render_mcq_performance(api_base: str, headers: dict):
    """Render MCQ performance analytics."""
    try:
        resp = requests.get(f"{api_base}/api/v1/mcq/latest", headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            _display_mcq_results(data)
        elif resp.status_code == 404:
            render_empty_state(
                title="Awaiting Assessment Battery Record",
                message="No completed technical mock sessions logged yet. Complete an interview in Section 03 to populate diagnostic telemetry.",
                meta_code="TELEMETRY // PENDING",
            )
            _show_demo_mcq()
        else:
            st.warning("⚠️ Telemetry service returned status: " + str(resp.status_code))
    except requests.ConnectionError:
        st.error("❌ Backend server communication failed.")
    except Exception as e:
        st.error(f"Error: {str(e)}")


def _display_mcq_results(data: dict):
    """Display MCQ results with editorial charts."""
    total = data.get("total_answered", 0)
    correct = data.get("total_correct", 0)
    percentage = data.get("score_percentage", 0)

    # Score header cards
    col1, col2, col3, col4 = st.columns(4, gap="medium")
    with col1:
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.1rem; border-radius: 4px;">
                <div style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-tertiary);">RAW TALLY</div>
                <div style="font-family: var(--font-serif); font-size: 2.2rem; color: var(--ink-charcoal); line-height: 1.1;">{correct} / {total}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.1rem; border-radius: 4px;">
                <div style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-tertiary);">ACCURACY</div>
                <div style="font-family: var(--font-serif); font-size: 2.2rem; color: var(--ink-charcoal); line-height: 1.1;">{percentage}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        grade = "HONORS" if percentage >= 80 else "PROFICIENT" if percentage >= 60 else "DEVELOPING" if percentage >= 40 else "CRITICAL"
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.1rem; border-radius: 4px;">
                <div style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-tertiary);">DIAGNOSTIC</div>
                <div style="font-family: var(--font-mono); font-size: 1.1rem; font-weight: 700; color: var(--accent-red); margin-top: 0.4rem;">{grade}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col4:
        sess_id = data.get("session_id", "SESS-0000")[:10]
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.1rem; border-radius: 4px;">
                <div style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-tertiary);">BATTERY ID</div>
                <div style="font-family: var(--font-mono); font-size: 1.1rem; font-weight: 600; color: var(--ink-charcoal); margin-top: 0.4rem;">{sess_id}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Topic breakdown charts
    topic_breakdown = data.get("topic_breakdown", {})
    if topic_breakdown:
        st.markdown("---")
        st.markdown("### Domain Performance Visualization")

        chart_col1, chart_col2 = st.columns(2, gap="large")
        topics = list(topic_breakdown.keys())
        scores = list(topic_breakdown.values())

        with chart_col1:
            # Editorial Radar chart
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=scores + [scores[0]],
                theta=topics + [topics[0]],
                fill="toself",
                name="Score",
                line=dict(color="#D9381E", width=2),
                fillcolor="rgba(217, 56, 30, 0.12)",
            ))
            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 100], linecolor="#D8D1C5", gridcolor="#EFEBE3"),
                    angularaxis=dict(linecolor="#D8D1C5", gridcolor="#EFEBE3"),
                    bgcolor="#FFFFFF",
                ),
                paper_bgcolor="#FFFFFF",
                plot_bgcolor="#FFFFFF",
                title=dict(text="Competency Polar Map", font=dict(family="Instrument Serif", size=20, color="#141413")),
                height=380,
                showlegend=False,
                margin=dict(l=40, r=40, t=50, b=40),
            )
            st.plotly_chart(fig_radar, use_container_width=True)

        with chart_col2:
            # Editorial Bar chart
            colors = ["#2D5A27" if s >= 70 else "#D9381E" for s in scores]
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                x=scores, y=topics, orientation="h",
                marker_color=colors,
                text=[f"{s:.0f}%" for s in scores],
                textposition="auto",
            ))
            fig_bar.update_layout(
                title=dict(text="Topic Proficiency Index (Benchmark: 70%)", font=dict(family="Instrument Serif", size=20, color="#141413")),
                xaxis=dict(range=[0, 100], gridcolor="#EFEBE3", linecolor="#D8D1C5"),
                yaxis=dict(linecolor="#D8D1C5"),
                paper_bgcolor="#FFFFFF",
                plot_bgcolor="#FFFFFF",
                height=380,
                margin=dict(l=40, r=40, t=50, b=40),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    # Question review
    answers = data.get("answers", [])
    if answers:
        st.markdown("---")
        with st.expander("INSPECT COMPREHENSIVE QUESTION REPOSITORIES", expanded=False):
            for ans in answers:
                idx = ans.get("question_index", 0) + 1
                is_correct = ans.get("is_correct", False)
                status_color = "#2D5A27" if is_correct else "var(--accent-red)"
                status_text = "VERIFIED ACCURATE" if is_correct else "DEFICIENT"
                st.markdown(
                    f"""
                    <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.8rem 1.1rem; border-radius: 4px; margin-bottom: 0.6rem;">
                        <div style="display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 0.72rem;">
                            <span style="font-weight: 600; color: var(--ink-charcoal);">ITEM #{idx} — {ans.get('topic', 'General')} ({ans.get('response_time', 0):.1f}s)</span>
                            <span style="color: {status_color}; font-weight: 700;">{status_text}</span>
                        </div>
                        <div style="font-size: 0.92rem; color: var(--ink-charcoal); margin: 0.4rem 0;">{ans.get('question_text', '')}</div>
                        <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--ink-tertiary);">
                            CANDIDATE: {ans.get('user_answer', 'None')} | BENCHMARK: {ans.get('correct_answer', '')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def _render_ats_analysis(api_base: str, headers: dict):
    """Render ATS score and resume suggestions."""
    col_head, col_btn = st.columns([3, 1], gap="medium")
    with col_head:
        st.markdown(
            """
            <h3 style="margin: 0;">ATS Compatibility Audit</h3>
            <p style="font-size: 0.88rem; color: var(--ink-muted);">
                Synthesizes applicant tracking system keyword density, quantitative metrics, and section completeness.
            </p>
            """,
            unsafe_allow_html=True,
        )
    with col_btn:
        run_analysis = st.button("EXECUTE AUDIT →", type="primary", use_container_width=True, key="ats_analyze")

    if run_analysis:
        with st.spinner("Extracting tokens and evaluating match density..."):
            try:
                resp = requests.get(f"{api_base}/api/v1/score/ats/analyze", headers=headers, timeout=30)
                if resp.status_code == 200:
                    st.session_state.ats_data = resp.json()
                elif resp.status_code == 400:
                    st.warning("⚠️ Please ensure both Resume and Job Description are uploaded in Section 01.")
                    return
                else:
                    st.error(f"❌ Analysis failed: {resp.json().get('detail', '')}")
                    return
            except requests.ConnectionError:
                st.error("❌ Backend communication failure.")
                return
            except Exception as e:
                st.error(f"Error: {str(e)}")
                return

    if "ats_data" not in st.session_state:
        render_empty_state(
            title="Audit Uninitiated",
            message="Click 'Execute Audit' above to evaluate your uploaded resume against target job description requirements.",
            meta_code="ATS // STANDBY",
        )
        return

    data = st.session_state.ats_data
    ats_score = data.get("ats_score", 0)

    st.markdown("---")

    # Score metrics strip
    score_cols = st.columns(5, gap="small")
    metrics = [
        ("OVERALL ATS", f"{ats_score}%", "var(--accent-red)"),
        ("KEYWORD DENSITY", f"{data.get('keyword_score', 0)}%", "var(--ink-charcoal)"),
        ("SECTIONS", f"{data.get('section_score', 0)}%", "var(--ink-charcoal)"),
        ("ACTION VERBS", f"{data.get('verb_score', 0)}%", "var(--ink-charcoal)"),
        ("QUANTITATIVE", f"{data.get('quant_score', 0)}%", "var(--ink-charcoal)"),
    ]
    for idx, (label, val, color) in enumerate(metrics):
        with score_cols[idx]:
            st.markdown(
                f"""
                <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 0.9rem; border-radius: 4px; text-align: center;">
                    <div style="font-family: var(--font-mono); font-size: 0.65rem; color: var(--ink-tertiary);">{label}</div>
                    <div style="font-family: var(--font-serif); font-size: 1.8rem; color: {color}; line-height: 1.1; margin-top: 2px;">{val}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Keywords Dockets
    st.markdown("---")
    kw_col1, kw_col2 = st.columns(2, gap="large")

    with kw_col1:
        st.markdown(
            """
            <div style="margin-bottom: 0.6rem;">
                <span class="editorial-tag" style="background: rgba(45, 90, 39, 0.1); color: #2D5A27;">MATCHED // VERIFIED</span>
                <h4 style="margin: 0.3rem 0; font-family: var(--font-serif); font-size: 1.4rem;">Present Keywords</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )
        matched = data.get("matched_keywords", [])
        if matched:
            chips = "".join(f'<span class="meta-chip" style="margin: 2px;">{k}</span>' for k in matched)
            st.markdown(f"<div>{chips}</div>", unsafe_allow_html=True)
        else:
            st.caption("No direct keyword intersections discovered.")

    with kw_col2:
        st.markdown(
            """
            <div style="margin-bottom: 0.6rem;">
                <span class="editorial-tag">DEFICIENCY // INJECT</span>
                <h4 style="margin: 0.3rem 0; font-family: var(--font-serif); font-size: 1.4rem;">Missing Prerequisites</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )
        missing = data.get("missing_keywords", [])
        if missing:
            chips = "".join(f'<span class="meta-chip" style="margin: 2px; border-color: var(--accent-red); color: var(--accent-red);">{k}</span>' for k in missing)
            st.markdown(f"<div>{chips}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='color: #2D5A27; font-weight: 600;'>Zero missing keywords detected.</span>", unsafe_allow_html=True)

    # Resume improvement suggestions
    suggestions = data.get("suggestions", [])
    if suggestions:
        st.markdown("---")
        st.markdown("### Actionable Revision Guidance")
        for sug in suggestions:
            priority = sug.get("priority", "LOW")
            st.markdown(
                f"""
                <div class="docket-card">
                    <div style="display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 0.72rem; margin-bottom: 0.3rem;">
                        <span style="font-weight: 700; color: var(--accent-red);">[{priority}] {sug['title']}</span>
                        <span style="color: var(--ink-tertiary);">{sug.get('impact', '')}</span>
                    </div>
                    <div style="font-size: 0.9rem; color: var(--ink-muted);">{sug['description']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_study_plan(api_base: str, headers: dict):
    """Render remediation study plan based on weak areas."""
    st.markdown(
        """
        <h3 style="margin-bottom: 0.2rem;">Curricular Remediation Blueprint</h3>
        <p style="font-size: 0.88rem; color: var(--ink-muted);">
            Identifies conceptual sub-domains scoring under 70% and links directly to textbook reading hours.
        </p>
        """,
        unsafe_allow_html=True,
    )

    try:
        resp = requests.get(f"{api_base}/api/v1/mcq/latest", headers=headers, timeout=15)
        if resp.status_code != 200:
            render_empty_state(
                title="Awaiting Assessment Data",
                message="Complete a timed mock interview to activate customized syllabus remediation.",
                meta_code="REMEDIATION // STANDBY",
            )
            return

        data = resp.json()
        topic_breakdown = data.get("topic_breakdown", {})

        if not topic_breakdown:
            st.info("No topic telemetry available.")
            return

        weak_topics = {k: v for k, v in topic_breakdown.items() if v < 70}
        strong_topics = {k: v for k, v in topic_breakdown.items() if v >= 70}

        if not weak_topics:
            st.markdown(
                """
                <div style="background: rgba(45, 90, 39, 0.08); border: 1px solid #2D5A27; border-radius: 4px; padding: 1.25rem; margin: 1rem 0;">
                    <span class="editorial-tag" style="background: rgba(45, 90, 39, 0.15); color: #2D5A27;">STATUS // EXCELLENT</span>
                    <h4 style="margin: 0.4rem 0; color: #2D5A27;">Zero Conceptual Deficiencies Detected</h4>
                    <p style="margin: 0; color: var(--ink-charcoal);">All tested topics exceed the 70% institutional proficiency threshold.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            sorted_weak = sorted(weak_topics.items(), key=lambda x: x[1])
            for rank, (topic, score) in enumerate(sorted_weak, 1):
                severity = "CRITICAL" if score < 40 else "MODERATE" if score < 60 else "MILD"
                hours = 4 if score < 40 else 2 if score < 60 else 1
                st.markdown(
                    f"""
                    <div class="docket-card" style="border-left-width: 4px;">
                        <div style="display: flex; justify-content: space-between; align-items: baseline;">
                            <span class="editorial-tag">PRIORITY #{rank} // {severity}</span>
                            <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary);">EST. REVISION: {hours} HOURS</span>
                        </div>
                        <h4 style="font-family: var(--font-serif); font-size: 1.5rem; color: var(--ink-charcoal); margin: 0.4rem 0 0.2rem 0;">
                            {topic} — Current Mastery: {score:.0f}%
                        </h4>
                        <div style="font-family: var(--font-sans); font-size: 0.88rem; color: var(--ink-muted); margin-top: 0.5rem; line-height: 1.6;">
                            • Cross-reference primary course modules in <b>{topic}</b> using Curriculum Consultation Desk.<br>
                            • Execute targeted re-testing via Mock Interview Terminal focusing on <b>{topic}</b> queries.<br>
                            • Target Threshold: 80% benchmark proficiency.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        total_hours = sum(4 if v < 40 else 2 if v < 60 else 1 for v in weak_topics.values())
        col1, col2, col3 = st.columns(3, gap="medium")
        with col1:
            st.metric("Deficient Sub-Domains", len(weak_topics))
        with col2:
            st.metric("Proficient Sub-Domains", len(strong_topics))
        with col3:
            st.metric("Recommended Allocation", f"{total_hours} Hours")

    except Exception as e:
        st.error(f"Error: {str(e)}")


def _show_demo_mcq():
    """Show editorial demo charts for prospective students."""
    st.markdown("### Illustrative Telemetry (Preview Mode)")
    demo_topics = {
        "Python Core": 84, "Machine Learning": 72, "SQL Databases": 58,
        "Data Structures": 80, "Deep Learning": 52, "System Design": 66,
    }

    col1, col2 = st.columns(2, gap="large")
    topics = list(demo_topics.keys())
    scores = list(demo_topics.values())

    with col1:
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=scores + [scores[0]],
            theta=topics + [topics[0]],
            fill="toself",
            line=dict(color="#D9381E", width=2),
            fillcolor="rgba(217, 56, 30, 0.12)",
        ))
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], linecolor="#D8D1C5", gridcolor="#EFEBE3"),
                angularaxis=dict(linecolor="#D8D1C5", gridcolor="#EFEBE3"),
                bgcolor="#FFFFFF",
            ),
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
            title=dict(text="Sample Competency Radar", font=dict(family="Instrument Serif", size=20, color="#141413")),
            height=360,
            showlegend=False,
            margin=dict(l=40, r=40, t=50, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        colors = ["#2D5A27" if s >= 70 else "#D9381E" for s in scores]
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=scores, y=topics, orientation="h",
            marker_color=colors,
            text=[f"{s}%" for s in scores],
            textposition="auto",
        ))
        fig_bar.update_layout(
            title=dict(text="Sample Topic Proficiency Index", font=dict(family="Instrument Serif", size=20, color="#141413")),
            xaxis=dict(range=[0, 100], gridcolor="#EFEBE3", linecolor="#D8D1C5"),
            yaxis=dict(linecolor="#D8D1C5"),
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
            height=360,
            margin=dict(l=40, r=40, t=50, b=40),
        )
        st.plotly_chart(fig_bar, use_container_width=True)
