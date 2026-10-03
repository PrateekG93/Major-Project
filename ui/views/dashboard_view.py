"""
Performance Dashboard View
============================
Three tabs:
1. MCQ Performance — topic breakdown, charts, question review
2. ATS Analysis — ATS score, keyword match, resume suggestions
3. Study Plan — weak areas from MCQ with textbook recommendations
"""

import requests
import streamlit as st
import plotly.graph_objects as go


def render():
    st.markdown("# 📊 Performance Dashboard")
    st.markdown(
        "View your MCQ interview analytics, ATS resume score, "
        "and personalized improvement suggestions."
    )

    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")
    token = st.session_state.get("session_token", "")
    headers = {"x-session-token": token}

    tab1, tab2, tab3 = st.tabs([
        "🎯 MCQ Performance", "📄 ATS Analysis", "📚 Study Plan"
    ])

    # === Tab 1: MCQ Performance ===
    with tab1:
        _render_mcq_performance(api_base, headers)

    # === Tab 2: ATS Analysis ===
    with tab2:
        _render_ats_analysis(api_base, headers)

    # === Tab 3: Study Plan ===
    with tab3:
        _render_study_plan(api_base, headers)


def _render_mcq_performance(api_base: str, headers: dict):
    """Render MCQ performance analytics."""
    st.markdown("### 🎯 MCQ Interview Performance")

    # Try to auto-load latest session
    try:
        resp = requests.get(f"{api_base}/api/v1/mcq/latest", headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            _display_mcq_results(data)
        elif resp.status_code == 404:
            st.info("📝 No completed MCQ interviews yet. Take a mock interview to see your analytics here!")
            _show_demo_mcq()
        else:
            st.warning("Could not load results.")
    except requests.ConnectionError:
        st.error("Cannot connect to API server.")
    except Exception as e:
        st.error(f"Error: {str(e)}")


def _display_mcq_results(data: dict):
    """Display MCQ results with charts."""
    # Score header
    total = data.get("total_answered", 0)
    correct = data.get("total_correct", 0)
    percentage = data.get("score_percentage", 0)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 Score", f"{correct}/{total}")
    col2.metric("📈 Percentage", f"{percentage}%")

    if percentage >= 80:
        grade = "🏆 Excellent"
    elif percentage >= 60:
        grade = "✅ Good"
    elif percentage >= 40:
        grade = "⚠️ Needs Work"
    else:
        grade = "❌ Poor"
    col3.metric("🎯 Grade", grade)
    col4.metric("🆔 Session", data.get("session_id", "")[:12])

    # Topic breakdown charts
    topic_breakdown = data.get("topic_breakdown", {})
    if topic_breakdown:
        st.markdown("---")
        st.markdown("### 📊 Topic-wise Performance")

        chart_col1, chart_col2 = st.columns(2)

        topics = list(topic_breakdown.keys())
        scores = list(topic_breakdown.values())

        with chart_col1:
            # Radar chart
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=scores + [scores[0]],
                theta=topics + [topics[0]],
                fill="toself",
                name="Your Score",
                line_color="#667eea",
                fillcolor="rgba(102, 126, 234, 0.3)",
            ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                title="Skill Radar",
                height=400,
                showlegend=False,
            )
            st.plotly_chart(fig_radar, use_container_width=True)

        with chart_col2:
            # Bar chart
            colors = [
                "#28a745" if s >= 70 else "#ffc107" if s >= 50 else "#dc3545"
                for s in scores
            ]
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                x=scores, y=topics, orientation="h",
                marker_color=colors,
                text=[f"{s:.0f}%" for s in scores],
                textposition="auto",
            ))
            fig_bar.update_layout(
                title="Score by Topic",
                xaxis_title="Score (%)",
                xaxis=dict(range=[0, 100]),
                height=400,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    # Question review
    answers = data.get("answers", [])
    if answers:
        st.markdown("---")
        st.markdown("### 📝 Question-by-Question Review")
        for ans in answers:
            idx = ans.get("question_index", 0) + 1
            is_correct = ans.get("is_correct", False)
            is_timeout = ans.get("is_timeout", False)
            icon = "✅" if is_correct else "⏱️" if is_timeout else "❌"
            topic = ans.get("topic", "General")
            time_taken = ans.get("response_time", 0)

            with st.expander(f"{icon} Q{idx} — {topic} ({time_taken:.1f}s)"):
                st.markdown(f"**Question:** {ans.get('question_text', '')}")
                st.markdown(f"**Your Answer:** {ans.get('user_answer', 'No answer') or 'Timeout'}")
                st.markdown(f"**Correct Answer:** {ans.get('correct_answer', '')}")
                if ans.get("explanation"):
                    st.info(f"💡 {ans['explanation']}")


def _render_ats_analysis(api_base: str, headers: dict):
    """Render ATS score and resume suggestions."""
    st.markdown("### 📄 ATS Score Analysis")
    st.markdown("See how well your resume matches the Job Description for ATS screening.")

    if st.button("🔍 Analyze Resume vs JD", type="primary", use_container_width=True, key="ats_analyze"):
        with st.spinner("Analyzing your resume against the JD..."):
            try:
                resp = requests.get(f"{api_base}/api/v1/score/ats/analyze", headers=headers, timeout=30)
                if resp.status_code == 200:
                    st.session_state.ats_data = resp.json()
                elif resp.status_code == 400:
                    st.warning(f"⚠️ {resp.json().get('detail', 'Please upload resume and JD first.')}")
                    return
                else:
                    st.error(f"Error: {resp.json().get('detail', 'Analysis failed')}")
                    return
            except requests.ConnectionError:
                st.error("Cannot connect to API server.")
                return
            except Exception as e:
                st.error(f"Error: {str(e)}")
                return

    if "ats_data" not in st.session_state:
        st.info("Click the button above to analyze your resume against the JD.")
        return

    data = st.session_state.ats_data

    # ATS Score Gauge
    ats_score = data.get("ats_score", 0)
    st.markdown("---")

    score_cols = st.columns(5)
    score_cols[0].metric("🎯 ATS Score", f"{ats_score}%")
    score_cols[1].metric("🔑 Keywords", f"{data.get('keyword_score', 0)}%")
    score_cols[2].metric("📋 Sections", f"{data.get('section_score', 0)}%")
    score_cols[3].metric("💪 Action Verbs", f"{data.get('verb_score', 0)}%")
    score_cols[4].metric("📊 Metrics", f"{data.get('quant_score', 0)}%")

    # Score interpretation
    if ats_score >= 80:
        st.success("🟢 **Excellent match!** Your resume is well-aligned with this JD.")
    elif ats_score >= 60:
        st.warning("🟡 **Good match.** Some improvements can boost your chances.")
    elif ats_score >= 40:
        st.warning("🟠 **Moderate match.** Significant improvements recommended.")
    else:
        st.error("🔴 **Low match.** Major resume revisions needed for this role.")

    # Gauge chart
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=ats_score,
        title={"text": "ATS Compatibility Score"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#667eea"},
            "steps": [
                {"range": [0, 40], "color": "#ffcccc"},
                {"range": [40, 60], "color": "#fff3cd"},
                {"range": [60, 80], "color": "#d4edda"},
                {"range": [80, 100], "color": "#c3e6cb"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": 70,
            },
        },
    ))
    fig_gauge.update_layout(height=300)
    st.plotly_chart(fig_gauge, use_container_width=True)

    # Matched vs Missing Keywords
    st.markdown("---")
    kw_col1, kw_col2 = st.columns(2)

    with kw_col1:
        st.markdown("### ✅ Matched Keywords")
        matched = data.get("matched_keywords", [])
        if matched:
            st.markdown(", ".join(f"`{k}`" for k in matched))
        else:
            st.info("No keyword matches found.")

    with kw_col2:
        st.markdown("### ❌ Missing Keywords")
        missing = data.get("missing_keywords", [])
        if missing:
            st.markdown(", ".join(f"`{k}`" for k in missing))
        else:
            st.success("No missing keywords!")

    # Technical skills breakdown
    tech = data.get("technical_match", {})
    if tech.get("found") or tech.get("missing"):
        st.markdown("---")
        tech_col1, tech_col2 = st.columns(2)
        with tech_col1:
            st.markdown("### 💻 Technical Skills Found")
            for s in tech.get("found", []):
                st.markdown(f"✅ {s}")
        with tech_col2:
            st.markdown("### 🔧 Technical Skills Missing")
            for s in tech.get("missing", []):
                st.markdown(f"❌ {s}")

    # Resume Improvement Suggestions
    suggestions = data.get("suggestions", [])
    if suggestions:
        st.markdown("---")
        st.markdown("### 💡 Resume Improvement Suggestions")

        for sug in suggestions:
            priority = sug.get("priority", "LOW")
            icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(priority, "⚪")

            with st.expander(f"{icon} [{priority}] {sug['title']}"):
                st.markdown(sug["description"])
                if sug.get("impact"):
                    st.caption(f"💡 Impact: {sug['impact']}")


def _render_study_plan(api_base: str, headers: dict):
    """Render study plan based on MCQ weak areas."""
    st.markdown("### 📚 Study Plan")
    st.markdown("Based on your MCQ interview weak areas, here's what to focus on.")

    # Get MCQ data
    try:
        resp = requests.get(f"{api_base}/api/v1/mcq/latest", headers=headers, timeout=15)
        if resp.status_code != 200:
            st.info("Complete an MCQ interview first to get a personalized study plan.")
            return

        data = resp.json()
        topic_breakdown = data.get("topic_breakdown", {})

        if not topic_breakdown:
            st.info("No topic data available.")
            return

        # Identify weak topics (below 70%)
        weak_topics = {k: v for k, v in topic_breakdown.items() if v < 70}
        strong_topics = {k: v for k, v in topic_breakdown.items() if v >= 70}

        if not weak_topics:
            st.success("🎉 Great job! No weak areas detected. Keep practicing to maintain your skills.")
        else:
            # Sort by weakness
            sorted_weak = sorted(weak_topics.items(), key=lambda x: x[1])

            for rank, (topic, score) in enumerate(sorted_weak, 1):
                severity = "Critical" if score < 40 else "Moderate" if score < 60 else "Mild"
                icon = "🔴" if score < 40 else "🟡" if score < 60 else "🟠"
                hours = 4 if score < 40 else 2 if score < 60 else 1

                with st.expander(f"{icon} #{rank} {topic} — {score:.0f}% ({severity})"):
                    st.markdown(f"**Current Score:** {score:.0f}%")
                    st.markdown(f"**Target Score:** 80%")
                    st.markdown(f"**Estimated Study Time:** {hours} hours")
                    st.markdown("---")
                    st.markdown("**📝 Action Items:**")
                    st.markdown(f"- Review {topic} fundamentals from your course textbooks")
                    st.markdown(f"- Practice {topic} MCQs on platforms like GeeksforGeeks, LeetCode")
                    st.markdown(f"- Re-attempt the interview focusing on {topic} questions")
                    st.markdown(f"- Ask clarifying questions in the Academic Q&A section")

        # Summary
        st.markdown("---")
        st.markdown("### 📈 Overall Summary")
        total_hours = sum(4 if v < 40 else 2 if v < 60 else 1 for v in weak_topics.values())
        col1, col2, col3 = st.columns(3)
        col1.metric("⚠️ Weak Topics", len(weak_topics))
        col2.metric("✅ Strong Topics", len(strong_topics))
        col3.metric("📚 Est. Study Hours", f"{total_hours}h")

    except requests.ConnectionError:
        st.error("Cannot connect to API server.")
    except Exception as e:
        st.error(f"Error: {str(e)}")


def _show_demo_mcq():
    """Show a demo MCQ dashboard."""
    st.markdown("---")
    st.markdown("### 📈 Demo Dashboard Preview")
    st.caption("Sample data. Complete an MCQ interview to see real results.")

    demo_topics = {
        "Python": 82, "Machine Learning": 74, "SQL": 61,
        "Data Structures": 78, "Deep Learning": 55, "System Design": 68,
    }

    col1, col2 = st.columns(2)
    topics = list(demo_topics.keys())
    scores = list(demo_topics.values())

    with col1:
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=scores + [scores[0]],
            theta=topics + [topics[0]],
            fill="toself",
            line_color="#667eea",
            fillcolor="rgba(102, 126, 234, 0.2)",
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            title="Sample Skill Radar",
            height=400,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        colors = [
            "#28a745" if s >= 70 else "#ffc107" if s >= 50 else "#dc3545"
            for s in scores
        ]
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=scores, y=topics, orientation="h",
            marker_color=colors,
            text=[f"{s}%" for s in scores],
            textposition="auto",
        ))
        fig_bar.update_layout(
            title="Sample Score Breakdown",
            xaxis=dict(range=[0, 100]),
            height=400,
        )
        st.plotly_chart(fig_bar, use_container_width=True)
