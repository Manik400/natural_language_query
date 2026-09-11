"""
Streamlit entry point (also the Streamlit Community Cloud main file).

Two pages, sharing the styles below:
  - Search         (ui/search_page.py)   plain-English query → filters → matching events
  - Data Explorer  (ui/data_explorer.py) browse the whole dummy dataset
"""

import os
import time

import streamlit as st

# Streamlit Cloud servers run on UTC, but the time resolvers and transform.py
# work in Indian wall-clock time.
os.environ.setdefault("TZ", "Asia/Kolkata")
if hasattr(time, "tzset"):
    time.tzset()

# Make root-level secrets (.streamlit/secrets.toml or the Cloud "Secrets" box)
# visible to config.Settings, which reads environment variables.
try:
    for _key, _value in st.secrets.items():
        if isinstance(_value, (str, int, float)):
            os.environ.setdefault(_key, str(_value))
except Exception:  # no secrets configured → offline rules mode
    pass

st.set_page_config(
    page_title="NLI · Query Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;1,400&family=Outfit:wght@300;400;500;600;700;800&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] {
    background: #f4f6fa !important;
    color: #1a2133;
    font-family: 'Outfit', sans-serif;
}
[data-testid="stHeader"]     { background: #f4f6fa !important; }
[data-testid="stDecoration"] { display: none; }
.block-container { padding: 2.5rem 3rem 4rem 3rem !important; max-width: 1440px !important; }

/* ── Hero ── */
.hero { margin-bottom: 2.5rem; }
.hero-eyebrow {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    letter-spacing: 0.22em;
    color: #8a9ab8;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
}
.hero-title {
    font-size: 3.2rem;
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.04em;
    color: #0f1829;
    margin-bottom: 0.5rem;
}
.hero-title span { color: #1a5cf0; }
.hero-desc {
    font-size: 1rem;
    color: #5a6a88;
    font-weight: 400;
    max-width: 520px;
}

/* ── Input ── */
.stTextArea > label { display: none !important; }
.stTextArea textarea {
    background: #ffffff !important;
    border: 1.5px solid #d0d8ea !important;
    border-radius: 10px !important;
    color: #1a2133 !important;
    font-family: 'Outfit', sans-serif !important;
    font-size: 1rem !important;
    line-height: 1.6 !important;
    padding: 1rem 1.2rem !important;
    transition: border-color 0.2s !important;
    resize: none !important;
}
.stTextArea textarea:focus {
    border-color: #1a5cf0 !important;
    box-shadow: 0 0 0 3px rgba(26,92,240,0.1) !important;
}
.stTextArea textarea::placeholder { color: #b0bbd0 !important; }

/* ── Button ── */
.stButton > button {
    background: #1a5cf0 !important;
    color: #fff !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.03em !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.7rem 2.5rem !important;
    width: 100% !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    background: #0f4ad8 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(26,92,240,0.25) !important;
}

/* ── Cards ── */
.card {
    background: #ffffff;
    border: 1.5px solid #dde4f0;
    border-radius: 14px;
    padding: 1.6rem 1.8rem;
    margin-bottom: 1.1rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.card-accent { border-top: 3px solid #1a5cf0; }

.card-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #8a9ab8;
    margin-bottom: 1.3rem;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-weight: 600;
}
.card-label::after {
    content: '';
    flex: 1;
    height: 1.5px;
    background: #eaeff8;
}

/* ── Time ── */
.time-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.time-cell {
    background: #f4f6fa;
    border: 1.5px solid #dde4f0;
    border-radius: 10px;
    padding: 1rem 1.2rem;
}
.time-cell-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #8a9ab8;
    margin-bottom: 0.5rem;
    font-weight: 600;
}
.time-cell-date {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.15rem;
    font-weight: 700;
    color: #0f1829;
    line-height: 1.2;
}
.time-cell-time {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.9rem;
    color: #5a6a88;
    margin-top: 0.25rem;
}
.time-meta {
    margin-top: 1.1rem;
    padding-top: 1rem;
    border-top: 1.5px solid #eaeff8;
    display: flex;
    gap: 1.8rem;
    flex-wrap: wrap;
}
.time-meta-item {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #8a9ab8;
    font-weight: 500;
}
.time-meta-item span { color: #1a5cf0; font-weight: 600; }

/* ── Video groups ── */
.vgroup { margin-bottom: 1.5rem; }
.vgroup:last-child { margin-bottom: 0; }

.vgroup-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 0.7rem;
    gap: 0.5rem;
}
.vgroup-name {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.9rem;
    font-weight: 700;
    color: #1a3a7a;
    letter-spacing: 0.04em;
}
.vgroup-badge {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    border-radius: 4px;
    padding: 0.15rem 0.6rem;
    font-weight: 600;
    white-space: nowrap;
    flex-shrink: 0;
}

/* Token / Slice info table */
.vgroup-info {
    background: #f4f6fa;
    border: 1.5px solid #dde4f0;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 0.75rem;
}
.vgroup-info-row {
    display: flex;
    align-items: center;
    border-bottom: 1px solid #eaeff8;
}
.vgroup-info-row:last-child { border-bottom: none; }
.vgroup-info-key {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #8a9ab8;
    font-weight: 600;
    padding: 0.38rem 0.75rem;
    width: 42%;
    border-right: 1px solid #eaeff8;
    flex-shrink: 0;
}
.vgroup-info-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    font-weight: 700;
    padding: 0.38rem 0.75rem;
}
.vgroup-info-val.token { color: #1a5cf0; }
.vgroup-info-val.slice { color: #16803a; }

.cam-wrap { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.cam-chip {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #3a5080;
    background: #eef1f8;
    border: 1px solid #d0d8ea;
    border-radius: 5px;
    padding: 0.22rem 0.65rem;
    white-space: nowrap;
    font-weight: 500;
}
.vgroup-empty {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    color: #8a9ab8;
    font-style: italic;
}

/* ── Event cards ── */
.ev-card {
    background: #f8faff;
    border: 1.5px solid #dde4f0;
    border-radius: 12px;
    padding: 1.3rem 1.5rem;
    margin-bottom: 1rem;
}
.ev-card:last-child { margin-bottom: 0; }
.ev-name {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #1a4a9a;
    margin-bottom: 1rem;
    padding-bottom: 0.8rem;
    border-bottom: 1.5px solid #dde4f0;
}
.field-table { width: 100%; border-collapse: collapse; }
.field-row-tr { border-bottom: 1px solid #eef1f8; }
.field-row-tr:last-child { border-bottom: none; }
.field-td { padding: 0.45rem 0; vertical-align: middle; }
.f-name {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    color: #2a3a5a;
    padding-right: 1rem;
    width: 165px;
    font-weight: 500;
}
.f-op {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #5a6a88;
    background: #eef1f8;
    border: 1px solid #d0d8ea;
    border-radius: 4px;
    padding: 0.18rem 0.55rem;
    letter-spacing: 0.05em;
    white-space: nowrap;
    width: 1%;
    padding-right: 1rem;
    font-weight: 600;
}
.f-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    color: #1a2a4a;
    padding-right: 1rem;
    font-weight: 600;
}
.f-val-t  { color: #16803a; background: #e8faf0; padding: 0.1rem 0.5rem; border-radius: 4px; border: 1px solid #bbf0d0; }
.f-val-f  { color: #c0392b; background: #fdecea; padding: 0.1rem 0.5rem; border-radius: 4px; border: 1px solid #f5b8b2; }
.f-val-n  { color: #1a5cf0; background: #eaf0ff; padding: 0.1rem 0.5rem; border-radius: 4px; border: 1px solid #b8cbf8; }
.f-snip {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #7a90b8;
    font-style: italic;
    padding-left: 0.6rem;
    border-left: 2px solid #d0d8ea;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 200px;
}
.ev-qpart {
    margin-top: 0.9rem;
    padding-top: 0.8rem;
    border-top: 1px solid #eaeff8;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #8a9ab8;
    font-style: italic;
    line-height: 1.6;
}
.ev-qpart b { color: #1a5cf0; font-style: normal; font-weight: 600; }

/* ── Attribute Conditions ── */
.attr-cond-card {
    background: #ffffff;
    border: 1.5px solid #dde4f0;
    border-top: 3px solid #1a5cf0;
    border-radius: 14px;
    padding: 1.6rem 1.8rem;
    margin-bottom: 1.1rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.attr-cond-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #8a9ab8;
    margin-bottom: 1.3rem;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-weight: 600;
}
.attr-cond-label::after {
    content: '';
    flex: 1;
    height: 1.5px;
    background: #eaeff8;
}
.attr-cond-type {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: #eaf0ff;
    border: 1.5px solid #b8cbf8;
    border-radius: 6px;
    padding: 0.28rem 0.9rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 700;
    color: #1a5cf0;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 1.1rem;
}
.attr-cond-table { width: 100%; border-collapse: collapse; }
.attr-cond-row { border-bottom: 1px solid #eef1f8; }
.attr-cond-row:last-child { border-bottom: none; }
.attr-cond-td { padding: 0.5rem 0; vertical-align: middle; }
.ac-key {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    color: #2a3a5a;
    font-weight: 600;
    padding-right: 1rem;
    width: 130px;
}
.ac-op {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #1a5cf0;
    background: #eaf0ff;
    border: 1px solid #b8cbf8;
    border-radius: 4px;
    padding: 0.18rem 0.55rem;
    font-weight: 700;
    white-space: nowrap;
    width: 1%;
    padding-right: 1rem;
}
.ac-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    color: #1a2a4a;
    font-weight: 700;
    padding-right: 1rem;
}
.ac-raw {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #7a90b8;
    font-style: italic;
    padding-left: 0.6rem;
    border-left: 2px solid #b8cbf8;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 200px;
}

/* ── Events row ── */
.events-row-card {
    background: #ffffff;
    border: 1.5px solid #dde4f0;
    border-top: 3px solid #1a5cf0;
    border-radius: 14px;
    padding: 1.6rem 1.8rem;
    margin-bottom: 1.1rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.events-inner-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 1rem;
}

/* ── Status ── */
.status-ok {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: #e8faf0;
    border: 1.5px solid #a0e0b8;
    border-radius: 7px;
    padding: 0.35rem 1.1rem 0.35rem 0.8rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #16803a;
    font-weight: 600;
    margin-bottom: 1.8rem;
}
.status-ok::before { content: '●'; font-size: 0.55rem; }
.status-irr {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: #fdecea;
    border: 1.5px solid #f5b8b2;
    border-radius: 7px;
    padding: 0.35rem 1.1rem 0.35rem 0.8rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #c0392b;
    font-weight: 600;
    margin-bottom: 1.8rem;
}
.status-irr::before { content: '●'; font-size: 0.55rem; }

/* ── Applied-filter chips & result count (Search page) ── */
.filter-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.1rem; }
.filter-chip {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    background: #eef1f8;
    border: 1px solid #d0d8ea;
    border-radius: 6px;
    padding: 0.3rem 0.65rem;
    color: #2a3a5a;
}
.filter-chip b { color: #1a5cf0; font-weight: 600; margin-right: 0.35rem; }
.result-count { font-size: 2.6rem; font-weight: 800; letter-spacing: -0.03em; color: #0f1829; line-height: 1; }
.result-sub { font-size: 0.9rem; color: #5a6a88; margin: 0.35rem 0 1.1rem 0; }
.engine-note { font-size: 0.82rem; color: #5a6a88; margin-top: 0.4rem; }

/* ── Stat tiles (Data Explorer) ── */
.stat-grid { display: grid; grid-template-columns: 1.4fr 1fr 1fr 1fr; gap: 1rem; margin: 0.4rem 0 1.1rem 0; }
.stat-tile {
    background: #ffffff;
    border: 1.5px solid #dde4f0;
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.stat-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.66rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #8a9ab8;
    font-weight: 600;
    margin-bottom: 0.5rem;
}
.stat-value { font-size: 1.9rem; font-weight: 700; color: #0f1829; line-height: 1.1; }
.stat-tile.hero { border-top: 3px solid #1a5cf0; }
.stat-tile.hero .stat-value { font-size: 3.2rem; font-weight: 800; letter-spacing: -0.03em; }
.stat-note { font-size: 0.8rem; color: #5a6a88; margin-top: 0.35rem; }
@media (max-width: 900px) { .stat-grid { grid-template-columns: 1fr 1fr; } }
</style>
""",
    unsafe_allow_html=True,
)

pages = [
    st.Page("ui/search_page.py", title="Search", icon=":material/search:", default=True),
    st.Page("ui/data_explorer.py", title="Data Explorer", icon=":material/table_view:"),
]
st.navigation(pages, position="top").run()
