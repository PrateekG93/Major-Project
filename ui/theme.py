"""
Editorial Design System for Academic & Career Copilot
=====================================================
Design Tokens:
- Background: Warm off-white / bone (#F5F2EC)
- Surface Paper: #EDE8DE
- Elevated Card: #FFFFFF
- Deep Charcoal Ink: #141413
- Muted Ink: #5A5852
- Subtle Hairline Border: #D8D1C5
- Single Accent (Vermilion): #D9381E
- Accent Soft: rgba(217, 56, 30, 0.08)
- Focus Ring: rgba(217, 56, 30, 0.25)
- Typography: 'Instrument Serif' (Display), 'Inter' (Body), 'JetBrains Mono' (Meta)
- Motion: Weighted spring physics cubic-bezier(0.16, 1, 0.3, 1)
"""

import streamlit as st


EDITORIAL_CSS = """
<style>
/* =====================================================================
   GOOGLE FONTS IMPORT
   ===================================================================== */
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

/* =====================================================================
   CORE DESIGN TOKENS & RESET
   ===================================================================== */
:root {
    --bg-bone: #F5F2EC;
    --bg-paper: #EFEBE3;
    --bg-card: #FFFFFF;
    --ink-charcoal: #141413;
    --ink-muted: #5A5852;
    --ink-tertiary: #8A8780;
    --border-subtle: #D8D1C5;
    --border-strong: #141413;
    --accent-red: #D9381E;
    --accent-red-hover: #B82B14;
    --accent-soft: rgba(217, 56, 30, 0.08);
    --font-serif: 'Instrument Serif', Georgia, serif;
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-mono: 'JetBrains Mono', SFMono-Regular, Consolas, monospace;
    --ease-spring: cubic-bezier(0.16, 1, 0.3, 1);
    --ease-weighted: cubic-bezier(0.25, 1, 0.5, 1);
}

/* Base canvas background & typography */
html, body, [data-testid="stAppViewContainer"] {
    background-color: var(--bg-bone) !important;
    color: var(--ink-charcoal) !important;
    font-family: var(--font-sans) !important;
    -webkit-font-smoothing: antialiased;
}

[data-testid="stHeader"] {
    background: transparent !important;
}

.block-container {
    padding-top: 1.75rem !important;
    padding-bottom: 3rem !important;
    max-width: 1220px !important;
}

/* =====================================================================
   SIDEBAR EDITORIAL STYLING
   ===================================================================== */
[data-testid="stSidebar"] {
    background-color: var(--bg-paper) !important;
    border-right: 1px solid var(--border-subtle) !important;
    padding-top: 1rem !important;
}

[data-testid="stSidebar"] hr {
    border-color: var(--border-subtle) !important;
    margin: 1rem 0 !important;
}

[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 {
    font-family: var(--font-serif) !important;
    color: var(--ink-charcoal) !important;
    letter-spacing: -0.01em;
}

[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown li {
    color: var(--ink-muted) !important;
    font-size: 0.92rem;
}

/* Sidebar navigation buttons */
[data-testid="stSidebar"] button {
    border: 1px solid var(--border-subtle) !important;
    background-color: var(--bg-card) !important;
    color: var(--ink-charcoal) !important;
    font-family: var(--font-mono) !important;
    font-size: 0.8rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    border-radius: 4px !important;
    padding: 0.55rem 0.85rem !important;
    margin-bottom: 0.4rem !important;
    box-shadow: 0 1px 2px rgba(20, 20, 19, 0.03) !important;
    transition: all 0.2s var(--ease-spring) !important;
}

[data-testid="stSidebar"] button:hover {
    border-color: var(--ink-charcoal) !important;
    transform: translateY(-1px);
    box-shadow: 0 3px 8px rgba(20, 20, 19, 0.06) !important;
}

[data-testid="stSidebar"] button:active {
    transform: translateY(1px) scale(0.99);
}

[data-testid="stSidebar"] button[kind="primary"] {
    background-color: var(--ink-charcoal) !important;
    color: var(--bg-bone) !important;
    border-color: var(--ink-charcoal) !important;
    font-weight: 600 !important;
}

/* =====================================================================
   TYPOGRAPHY HIERARCHY
   ===================================================================== */
h1 {
    font-family: var(--font-serif) !important;
    font-weight: 400 !important;
    font-size: 2.85rem !important;
    line-height: 1.15 !important;
    letter-spacing: -0.02em !important;
    color: var(--ink-charcoal) !important;
    margin-bottom: 0.6rem !important;
}

h2 {
    font-family: var(--font-serif) !important;
    font-weight: 400 !important;
    font-size: 2.1rem !important;
    line-height: 1.25 !important;
    letter-spacing: -0.015em !important;
    color: var(--ink-charcoal) !important;
    margin-top: 1.4rem !important;
    margin-bottom: 0.5rem !important;
}

h3 {
    font-family: var(--font-sans) !important;
    font-weight: 600 !important;
    font-size: 1.25rem !important;
    letter-spacing: -0.01em !important;
    color: var(--ink-charcoal) !important;
    margin-top: 1.2rem !important;
    margin-bottom: 0.4rem !important;
}

p, li {
    font-family: var(--font-sans) !important;
    color: var(--ink-muted) !important;
    line-height: 1.65 !important;
    font-size: 0.96rem !important;
}

small, .stCaption, [data-testid="stCaptionContainer"] {
    font-family: var(--font-mono) !important;
    font-size: 0.78rem !important;
    color: var(--ink-tertiary) !important;
    letter-spacing: 0.02em !important;
}

hr {
    border: none !important;
    border-top: 1px solid var(--border-subtle) !important;
    margin: 1.75rem 0 !important;
}

/* =====================================================================
   BUTTONS & FORM CONTROLS
   ===================================================================== */
button[kind="primary"], .stButton > button[kind="primary"] {
    background-color: var(--accent-red) !important;
    color: #FFFFFF !important;
    border: 1px solid var(--accent-red) !important;
    border-radius: 4px !important;
    font-family: var(--font-mono) !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    padding: 0.6rem 1.2rem !important;
    transition: all 0.22s var(--ease-spring) !important;
    box-shadow: 0 1px 3px rgba(217, 56, 30, 0.2) !important;
}

button[kind="primary"]:hover, .stButton > button[kind="primary"]:hover {
    background-color: var(--accent-red-hover) !important;
    border-color: var(--accent-red-hover) !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(217, 56, 30, 0.25) !important;
}

button[kind="primary"]:active, .stButton > button[kind="primary"]:active {
    transform: translateY(1px) scale(0.99);
}

button[kind="secondary"], .stButton > button[kind="secondary"] {
    background-color: var(--bg-card) !important;
    color: var(--ink-charcoal) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 4px !important;
    font-family: var(--font-mono) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    padding: 0.6rem 1.2rem !important;
    transition: all 0.22s var(--ease-spring) !important;
    box-shadow: 0 1px 2px rgba(20, 20, 19, 0.04) !important;
}

button[kind="secondary"]:hover, .stButton > button[kind="secondary"]:hover {
    border-color: var(--ink-charcoal) !important;
    color: var(--ink-charcoal) !important;
    transform: translateY(-1px);
    box-shadow: 0 3px 8px rgba(20, 20, 19, 0.06) !important;
}

/* Inputs, text areas, and selects */
input[type="text"], input[type="password"], textarea, [data-baseweb="input"] input {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 4px !important;
    color: var(--ink-charcoal) !important;
    font-family: var(--font-sans) !important;
    font-size: 0.95rem !important;
    padding: 0.55rem 0.85rem !important;
    transition: border-color 0.18s ease, box-shadow 0.18s ease !important;
}

input:focus, textarea:focus {
    border-color: var(--accent-red) !important;
    box-shadow: 0 0 0 3px var(--accent-soft) !important;
    outline: none !important;
}

/* =====================================================================
   EXPANDERS, CARDS, & CONTAINERS
   ===================================================================== */
[data-testid="stExpander"] {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 6px !important;
    box-shadow: 0 1px 3px rgba(20, 20, 19, 0.03) !important;
    margin-bottom: 0.85rem !important;
    transition: border-color 0.2s ease !important;
}

[data-testid="stExpander"]:hover {
    border-color: #B5ACA0 !important;
}

[data-testid="stExpander"] summary {
    font-family: var(--font-mono) !important;
    font-size: 0.86rem !important;
    letter-spacing: 0.02em !important;
    color: var(--ink-charcoal) !important;
    padding: 0.75rem 1rem !important;
}

/* Metric blocks */
[data-testid="stMetric"] {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 6px !important;
    padding: 1rem 1.25rem !important;
    box-shadow: 0 1px 3px rgba(20, 20, 19, 0.03) !important;
}

[data-testid="stMetricLabel"] {
    font-family: var(--font-mono) !important;
    font-size: 0.75rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: var(--ink-tertiary) !important;
}

[data-testid="stMetricValue"] {
    font-family: var(--font-serif) !important;
    font-size: 2.2rem !important;
    font-weight: 400 !important;
    color: var(--ink-charcoal) !important;
    line-height: 1.1 !important;
}

/* Tabs */
[data-baseweb="tab-list"] {
    border-bottom: 1px solid var(--border-subtle) !important;
    gap: 1.5rem !important;
}

[data-baseweb="tab"] {
    font-family: var(--font-mono) !important;
    font-size: 0.82rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: var(--ink-muted) !important;
    padding: 0.6rem 0.2rem !important;
    background: transparent !important;
    border: none !important;
}

[data-baseweb="tab"][aria-selected="true"] {
    color: var(--accent-red) !important;
    border-bottom: 2px solid var(--accent-red) !important;
    font-weight: 600 !important;
}

/* Chat Messages */
[data-testid="stChatMessage"] {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 6px !important;
    padding: 1.2rem !important;
    margin-bottom: 0.9rem !important;
    box-shadow: 0 1px 3px rgba(20, 20, 19, 0.02) !important;
    animation: editorialFadeIn 0.3s var(--ease-spring);
}

[data-testid="stChatInput"] textarea {
    border: 1px solid var(--border-subtle) !important;
    border-radius: 6px !important;
    background-color: var(--bg-card) !important;
    font-family: var(--font-sans) !important;
}

[data-testid="stChatInput"] textarea:focus {
    border-color: var(--accent-red) !important;
    box-shadow: 0 0 0 3px var(--accent-soft) !important;
}

/* Alerts / Banners */
[data-testid="stAlert"] {
    border-radius: 4px !important;
    border: 1px solid var(--border-subtle) !important;
    font-family: var(--font-sans) !important;
    font-size: 0.9rem !important;
}

/* =====================================================================
   EDITORIAL CUSTOM COMPONENTS & MICRO-INTERACTIONS
   ===================================================================== */
@keyframes editorialFadeIn {
    from {
        opacity: 0;
        transform: translateY(6px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes skeletonShimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}

.editorial-header-banner {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    border-bottom: 1px solid var(--ink-charcoal);
    padding-bottom: 0.9rem;
    margin-bottom: 1.5rem;
}

.editorial-tag {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent-red);
    background: var(--accent-soft);
    padding: 2px 8px;
    border-radius: 2px;
    display: inline-block;
}

.editorial-subhead {
    font-family: var(--font-serif);
    font-style: italic;
    color: var(--ink-muted);
    font-size: 1.15rem;
    margin-top: -0.3rem;
    margin-bottom: 1rem;
}

.meta-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--ink-muted);
    background: var(--bg-paper);
    border: 1px solid var(--border-subtle);
    padding: 3px 9px;
    border-radius: 3px;
    letter-spacing: 0.03em;
}

/* Skeleton Loading State */
.editorial-skeleton {
    background: linear-gradient(90deg, #EDE8DE 25%, #F7F5F0 50%, #EDE8DE 75%);
    background-size: 200% 100%;
    animation: skeletonShimmer 1.8s infinite;
    border-radius: 3px;
    height: 14px;
    margin-bottom: 8px;
}

/* Empty State Card */
.editorial-empty-state {
    background-color: var(--bg-card);
    border: 1px dashed var(--border-subtle);
    border-radius: 6px;
    padding: 2.75rem 2rem;
    text-align: center;
    margin: 1.5rem 0;
}

.editorial-empty-state h4 {
    font-family: var(--font-serif);
    font-size: 1.5rem;
    font-weight: 400;
    color: var(--ink-charcoal);
    margin: 0.5rem 0 0.3rem 0;
}

.editorial-empty-state p {
    font-family: var(--font-sans);
    font-size: 0.88rem;
    color: var(--ink-muted);
    max-width: 440px;
    margin: 0 auto;
}

/* Asymmetric Document Docket */
.docket-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-left: 3px solid var(--accent-red);
    border-radius: 4px;
    padding: 1.1rem 1.3rem;
    margin-bottom: 0.85rem;
    box-shadow: 0 1px 3px rgba(20, 20, 19, 0.03);
    transition: all 0.2s var(--ease-spring);
}

.docket-card:hover {
    border-color: #B5ACA0;
    border-left-color: var(--accent-red);
    transform: translateX(2px);
    box-shadow: 0 4px 12px rgba(20, 20, 19, 0.05);
}
</style>
"""


def apply_theme():
    """Inject the global editorial CSS design system into the Streamlit session."""
    st.markdown(EDITORIAL_CSS, unsafe_allow_html=True)


def render_editorial_title(title: str, subtitle: str = "", meta_tag: str = ""):
    """Render an asymmetric, high-contrast editorial section header."""
    meta_html = f'<span class="editorial-tag">{meta_tag}</span>' if meta_tag else ""
    st.markdown(
        f"""
        <div class="editorial-header-banner">
            <div>
                {meta_html}
                <h1 style="margin: 0.3rem 0 0 0;">{title}</h1>
            </div>
            <div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-tertiary); letter-spacing: 0.05em; text-align: right;">
                COPILOT // PR1107<br>VER // 2.4.0
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(f'<div class="editorial-subhead">{subtitle}</div>', unsafe_allow_html=True)


def render_empty_state(title: str, message: str, meta_code: str = "STATE // VOID"):
    """Render a graceful, publication-styled empty state for functional edge cases."""
    st.markdown(
        f"""
        <div class="editorial-empty-state">
            <span class="editorial-tag">{meta_code}</span>
            <h4>{title}</h4>
            <p>{message}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_skeleton_card():
    """Render an editorial loading skeleton block."""
    st.markdown(
        """
        <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 1.25rem; border-radius: 6px; margin: 0.8rem 0;">
            <div class="editorial-skeleton" style="width: 35%; height: 16px; margin-bottom: 12px;"></div>
            <div class="editorial-skeleton" style="width: 85%;"></div>
            <div class="editorial-skeleton" style="width: 70%;"></div>
            <div class="editorial-skeleton" style="width: 45%;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
