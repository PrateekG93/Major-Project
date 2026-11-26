"""
Centralized Interview Question Bank View
==========================================
Allows students to search & filter questions by Topic, Round (Coding / Technical / HR),
and Difficulty, browse topic collections, view reference answers, bookmark questions,
import custom JSON/CSV datasets, and launch directly into the Audio Interview Simulator.
"""

import html
import requests
import streamlit as st
from ui.theme import render_editorial_title, render_empty_state
from src.utils.text_utils import strip_html_markup


def render():
    render_editorial_title(
        title="Interview Question Bank",
        subtitle="Centralized, deduplicated interview repository organized across core computer science, AI/ML, and behavioral topics.",
        meta_tag="MODULE 04 // QUESTION REPOSITORY",
    )

    api_base = st.session_state.get("api_base_url", "http://127.0.0.1:8000")
    token = st.session_state.get("session_token", "")
    headers = {"x-session-token": token}

    if "qb_selected_topic" not in st.session_state:
        st.session_state.qb_selected_topic = "All"
    if "qb_page" not in st.session_state:
        st.session_state.qb_page = 1

    # Tabs: Search & Filter | Browse by Topic | Saved Bookmarks | Import Dataset
    tab_browse, tab_topics, tab_saved, tab_import = st.tabs([
        "01 — Search & Filter Bank",
        "02 — Browse by Topic",
        "03 — Saved Bookmarks",
        "04 — Import Dataset",
    ])

    with tab_browse:
        _render_search_explorer(api_base, headers, bookmarked_only=False, key_prefix="browse")

    with tab_topics:
        _render_topic_catalog(api_base, headers)

    with tab_saved:
        _render_search_explorer(api_base, headers, bookmarked_only=True, key_prefix="saved")

    with tab_import:
        _render_import_tab(api_base, headers)


def _render_topic_catalog(api_base: str, headers: dict):
    """Display interactive Topic cards (Easy / Medium / Hard breakdown)."""
    try:
        resp = requests.get(f"{api_base}/api/v1/questions/topics", headers=headers, timeout=10)
        if resp.status_code != 200:
            st.warning("Could not load topic catalog.")
            return
        topics = resp.json().get("topics", [])
    except requests.ConnectionError:
        st.error("❌ Backend server unreachable.")
        return
    except Exception as e:
        st.error(f"Error: {e}")
        return

    if not topics:
        render_empty_state(
            title="No Questions Indexed Yet",
            message="Seed the question bank from the Admin Portal or import a dataset.",
            meta_code="CATALOG // EMPTY",
        )
        return

    noticed_topic = st.session_state.pop("qb_topic_notice", None)
    if noticed_topic:
        st.info(f"Filtered **01 — Search & Filter Bank** by topic: **{noticed_topic}**. Click the **01 — Search & Filter Bank** tab above to view those questions.")

    st.markdown("### Curricular Topics Collection")
    cols = st.columns(3, gap="medium")
    for idx, tp in enumerate(topics):
        t_name = tp["topic"]
        q_cnt = tp["question_count"]
        easy_c = tp.get("easy_count", 0)
        med_c = tp.get("medium_count", 0)
        hard_c = tp.get("hard_count", 0)
        rounds = ", ".join(r.upper() for r in tp.get("rounds", [])) or "TECHNICAL"

        with cols[idx % 3]:
            jd_badge = (
                '<span class="meta-chip" style="background: rgba(217, 56, 30, 0.1); color: var(--accent-red); margin-left:6px;">JD MATCH</span>'
                if tp.get("is_jd_match")
                else ""
            )
            st.markdown(
                (
                    '<div class="docket-card">'
                    '<div style="display:flex; justify-content:space-between; align-items:baseline;">'
                    f'<span style="font-family: var(--font-serif); font-size: 1.35rem; color: var(--ink-charcoal);">{html.escape(t_name)}</span>'
                    f'<div><span class="editorial-tag">{q_cnt} Qs</span>{jd_badge}</div>'
                    "</div>"
                    '<div style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-tertiary); margin-top: 6px;">'
                    f"EASY: {easy_c} | MEDIUM: {med_c} | HARD: {hard_c}<br>"
                    f"ROUNDS: {html.escape(rounds)}"
                    "</div></div>"
                ),
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2, gap="small")
            with c1:
                if st.button("VIEW", key=f"open_top_{idx}", use_container_width=True, type="secondary"):
                    st.session_state["qb_pending_topic"] = t_name
                    st.session_state["qb_pending_scope"] = "jd" if tp.get("is_jd_match") else "all"
                    st.session_state["qb_topic_notice"] = t_name
                    st.session_state.qb_page = 1
                    st.rerun()
            with c2:
                if st.button("PRACTICE →", key=f"prac_top_{idx}", use_container_width=True, type="primary"):
                    st.session_state.audio_prefill_topic = t_name
                    st.session_state.current_page = "interview"
                    st.rerun()


def _render_search_explorer(api_base: str, headers: dict, bookmarked_only: bool, key_prefix: str):
    """Render Search, Topic, Round, Difficulty, Sort By controls and paginated question cards."""
    try:
        facets_resp = requests.get(f"{api_base}/api/v1/questions/filters", headers=headers, timeout=8)
        facets = facets_resp.json() if facets_resp.status_code == 200 else {}
    except Exception:
        facets = {}

    all_topics = facets.get("topics", [])
    jd_ctx = facets.get("jd_context", {}) or {}
    has_jd = bool(jd_ctx.get("has_jd") and jd_ctx.get("jd_topics"))
    jd_topics = jd_ctx.get("jd_topics", [])

    scope_param = "all"
    if not bookmarked_only:
        pending_scope = st.session_state.pop("qb_pending_scope", None)
        if pending_scope in ("jd", "all"):
            st.session_state.qb_domain_scope = pending_scope if has_jd else "all"
            st.session_state["qb_scope_radio"] = st.session_state.qb_domain_scope

        pending_topic = st.session_state.pop("qb_pending_topic", None)
        if pending_topic:
            st.session_state.qb_selected_topic = pending_topic
            st.session_state[f"{key_prefix}_topic"] = pending_topic

        if "qb_domain_scope" not in st.session_state:
            st.session_state.qb_domain_scope = "jd" if has_jd else "all"

        if has_jd:
            jd_label = f"JD-Related Domains First ({len(jd_topics)} matched)"
            all_label = f"All Domains ({len(all_topics)} topics)"
            scope_choice = st.radio(
                "Domain View",
                options=["jd", "all"],
                index=0 if st.session_state.qb_domain_scope == "jd" else 1,
                format_func=lambda v: jd_label if v == "jd" else all_label,
                horizontal=True,
                key="qb_scope_radio",
            )
            if scope_choice != st.session_state.qb_domain_scope:
                st.session_state.qb_domain_scope = scope_choice
                st.session_state.qb_page = 1
                st.session_state.qb_selected_topic = "All"
                st.session_state["browse_topic"] = "All"
            scope_param = st.session_state.qb_domain_scope

            role_str = jd_ctx.get("jd_role") or "Target Role"
            comp_str = f" @ {jd_ctx['jd_company']}" if jd_ctx.get("jd_company") else ""
            topics_preview = ", ".join(jd_topics[:4]) + ("..." if len(jd_topics) > 4 else "")
            if scope_param == "jd":
                st.caption(f"🎯 Prioritizing **{role_str}{comp_str}** JD domains: {topics_preview}")
            else:
                st.caption(f"🌐 Showing **All Domains** (JD-matched domains for **{role_str}{comp_str}** still ordered first under Relevance)")
        else:
            st.caption("Showing all 11 domains. Upload a Job Description in **01 — Upload Dossier** to prioritize JD-related questions first.")

    visible_topics = jd_topics if (not bookmarked_only and has_jd and scope_param == "jd") else all_topics
    topics_opts = ["All"] + visible_topics
    rounds_opts = ["All", "Coding", "Technical", "HR"]
    diff_opts = ["All", "easy", "medium", "hard"]

    default_topic_idx = 0
    if not bookmarked_only and st.session_state.get("qb_selected_topic") in topics_opts:
        default_topic_idx = topics_opts.index(st.session_state.qb_selected_topic)

    # Search & Sort
    c_search, c_sort = st.columns([3, 1], gap="medium")
    with c_search:
        q_text = st.text_input(
            "Search Questions, Topics, or Keywords",
            placeholder="e.g. distributed cache, normalization, binary search, leadership...",
            key=f"{key_prefix}_q",
        )
    with c_sort:
        sort_by = st.selectbox(
            "Sort By",
            options=["relevance", "frequency", "recent"],
            format_func=lambda x: {"relevance": "Relevance", "frequency": "Most Frequent", "recent": "Most Recent"}[x],
            key=f"{key_prefix}_sort",
        )

    # Remaining filters: Topic, Round, Difficulty
    fc1, fc2, fc3 = st.columns(3, gap="medium")
    with fc1:
        sel_topic = st.selectbox("Topic", topics_opts, index=default_topic_idx, key=f"{key_prefix}_topic")
    with fc2:
        sel_round = st.selectbox("Round", rounds_opts, key=f"{key_prefix}_round")
    with fc3:
        sel_diff = st.selectbox("Difficulty", diff_opts, key=f"{key_prefix}_diff")

    if not bookmarked_only:
        filter_sig = (scope_param, q_text, sort_by, sel_topic, sel_round, sel_diff)
        if st.session_state.get("qb_last_filters") != filter_sig:
            st.session_state.qb_last_filters = filter_sig
            st.session_state.qb_page = 1
        st.session_state.qb_selected_topic = sel_topic

    params = {
        "q": q_text,
        "topic": "" if sel_topic == "All" else sel_topic,
        "interview_round": "" if sel_round == "All" else sel_round,
        "difficulty": "" if sel_diff == "All" else sel_diff,
        "sort_by": sort_by,
        "page": st.session_state.qb_page,
        "page_size": 10,
        "bookmarked_only": bookmarked_only,
        "scope": scope_param,
    }

    try:
        resp = requests.get(f"{api_base}/api/v1/questions/search", params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            st.error(f"Failed to query question bank: {resp.json().get('detail', resp.status_code)}")
            return
        data = resp.json()
    except requests.ConnectionError:
        st.error("❌ Backend API unreachable.")
        return
    except Exception as e:
        st.error(f"Error: {e}")
        return

    total = data.get("total", 0)
    total_pages = data.get("total_pages", 1)
    items = data.get("items", [])

    st.markdown(
        f"<div style='font-family:var(--font-mono); font-size:0.75rem; color:var(--ink-tertiary); margin:0.5rem 0;'>"
        f"SHOWING {len(items)} OF {total} CANONICAL QUESTIONS (PAGE {st.session_state.qb_page} OF {total_pages})"
        f"</div>",
        unsafe_allow_html=True,
    )

    if not items:
        render_empty_state(
            title="No Matching Questions",
            message="Adjust your search query or filters to explore other questions in the bank.",
            meta_code="QUERY // 0 RESULTS",
        )
        return

    for item in items:
        cid = item["id"]
        clean_q = strip_html_markup(item["question_text"])
        topic_str = html.escape(item["topic"].upper())
        diff_str = html.escape(item["difficulty"].upper())
        tech_label = "TECHNICAL" if item.get("is_technical", True) else "NON-TECHNICAL"
        freq = item.get("frequency", 1)
        dups = item.get("duplicate_variations_count", 0)

        badges = (
            f'<span class="editorial-tag" style="margin-right:6px;">{topic_str}</span>'
            f'<span class="meta-chip" style="margin-right:6px;">{tech_label}</span>'
            f'<span class="meta-chip" style="margin-right:6px;">{diff_str}</span>'
        )
        for rnd in item.get("rounds", []):
            badges += f'<span class="meta-chip" style="margin-right:6px;">ROUND: {html.escape(rnd.upper())}</span>'

        st.markdown(
            (
                '<div style="background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 1.15rem 1.25rem; margin-bottom: 0.45rem;">'
                '<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:0.45rem;">'
                f"<div>{badges}</div>"
                f'<span style="font-family:var(--font-mono); font-size:0.7rem; color:var(--ink-tertiary);">FREQ: {freq} | MERGED VARIATIONS: {dups}</span>'
                "</div></div>"
            ),
            unsafe_allow_html=True,
        )
        st.markdown(f"**{clean_q}**")

        act_c1, act_c2, act_c3 = st.columns([2, 1, 1], gap="small")
        with act_c1:
            with st.expander("Sources & Reference Answer", expanded=False):
                if item.get("reference_answer"):
                    st.markdown(f"**Reference Answer:** {strip_html_markup(item['reference_answer'])}")
                if item.get("tags"):
                    st.caption("Tags: " + ", ".join(item["tags"]))
                if item.get("sources"):
                    st.markdown("**Round & Reference Metadata:**")
                    for src in item.get("sources", []):
                        rnd_lbl = src.get("interview_round") or "Technical"
                        url = src.get("source_url", "")
                        if url:
                            st.markdown(f"- Round: **{rnd_lbl}** — [Reference Link]({url})")
                        else:
                            st.markdown(f"- Round: **{rnd_lbl}**")

        with act_c2:
            is_bm = item.get("is_bookmarked", False)
            bm_label = "★ SAVED" if is_bm else "☆ SAVE / BOOKMARK"
            if st.button(bm_label, key=f"{key_prefix}_bm_{cid}", use_container_width=True, type="secondary"):
                try:
                    if is_bm:
                        requests.delete(f"{api_base}/api/v1/questions/{cid}/bookmark", headers=headers, timeout=5)
                    else:
                        requests.post(f"{api_base}/api/v1/questions/{cid}/bookmark", json={"notes": ""}, headers=headers, timeout=5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Bookmark error: {e}")

        with act_c3:
            if st.button("🎙️ PRACTICE →", key=f"{key_prefix}_prac_{cid}", use_container_width=True, type="primary"):
                st.session_state.audio_prefill_question = clean_q
                st.session_state.audio_prefill_topic = item["topic"]
                st.session_state.current_page = "interview"
                st.rerun()

    # Pagination controls
    p_col1, p_col2, p_col3 = st.columns([1, 2, 1])
    with p_col1:
        if st.button("← PREVIOUS", disabled=(st.session_state.qb_page <= 1), key=f"{key_prefix}_prev", use_container_width=True):
            st.session_state.qb_page -= 1
            st.rerun()
    with p_col2:
        st.markdown(
            f"<div style='text-align:center; font-family:var(--font-mono); font-size:0.8rem; padding-top:0.5rem;'>Page {st.session_state.qb_page} of {total_pages}</div>",
            unsafe_allow_html=True,
        )
    with p_col3:
        if st.button("NEXT →", disabled=(st.session_state.qb_page >= total_pages), key=f"{key_prefix}_next", use_container_width=True):
            st.session_state.qb_page += 1
            st.rerun()


def _render_import_tab(api_base: str, headers: dict):
    """Allow importing user-supplied JSON/CSV question datasets."""
    st.markdown("### Import JSON / CSV Interview Dataset")
    st.markdown(
        "Upload or paste structured interview questions (with `question_text`, `topic`, `round`, "
        "`difficulty`, `reference_answer`, and optional `tags` / `source_url`). "
        "All entries pass through multi-level exact, lexical, and semantic deduplication."
    )

    fmt = st.radio("Dataset Format", ["json", "csv"], horizontal=True, key="import_fmt")
    uploaded = st.file_uploader("Upload JSON or CSV file", type=["json", "csv"], key="import_file")
    pasted = st.text_area(
        "Or paste dataset content directly",
        height=180,
        placeholder='[{"question_text": "Explain CAP theorem.", "topic": "System Design", "round": "Technical", "difficulty": "medium", "reference_answer": "..."}]',
        key="import_paste",
    )

    if st.button("INGEST & DEDUPLICATE DATASET →", type="primary", use_container_width=True, key="import_submit"):
        raw_text = ""
        if uploaded is not None:
            raw_text = uploaded.read().decode("utf-8", errors="ignore")
        elif pasted.strip():
            raw_text = pasted.strip()

        if not raw_text:
            st.warning("Please upload a file or paste dataset content.")
            return

        with st.spinner("Running normalization, semantic embedding deduplication, and ingestion..."):
            try:
                resp = requests.post(
                    f"{api_base}/api/v1/questions/import",
                    json={"format": fmt, "content": raw_text},
                    headers=headers,
                    timeout=60,
                )
                if resp.status_code == 200:
                    stats = resp.json().get("stats", {})
                    st.success(
                        f"✅ Imported! New Canonical: `{stats.get('new_canonical', 0)}` | "
                        f"Exact Dupes Merged: `{stats.get('duplicate_exact', 0)}` | "
                        f"Lexical Dupes Merged: `{stats.get('duplicate_lexical', 0)}` | "
                        f"Semantic Dupes Merged: `{stats.get('duplicate_semantic', 0)}`"
                    )
                else:
                    st.error(f"❌ {resp.json().get('detail', 'Import failed')}")
            except Exception as e:
                st.error(f"Import error: {e}")
