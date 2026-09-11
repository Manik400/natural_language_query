import json

import requests
import streamlit as st

API_URL = "http://localhost:8081/pipeline"

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
</style>
""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def fmt_val(v):
    if isinstance(v, bool):
        cls = "f-val f-val-t" if v else "f-val f-val-f"
        return f'<span class="{cls}">{"true" if v else "false"}</span>'
    if isinstance(v, (int, float)):
        return f'<span class="f-val f-val-n">{v}</span>'
    return f'<span class="f-val">{v}</span>'


def render_events(extracted_fields, field_attrs) -> str:
    """Return HTML string for all extracted event field cards."""
    html = ""
    for ev in extracted_fields:
        name = ev["event_name"]
        fields = ev.get("relevant_fields", [])
        attr = field_attrs.get(name, {})
        snips = {f["field"]: f.get("query_snippet", "") for f in attr.get("fields", [])}
        qpart = attr.get("query_part", "")

        rows = ""
        for f in fields:
            fn = f.get("field", "")
            op = f.get("operator", "")
            val = f.get("value")
            snip = snips.get(fn, "")
            snip_td = (
                '<td class="field-td f-snip">"' + snip + '"</td>'
                if snip
                else '<td class="field-td"></td>'
            )
            rows += (
                '<tr class="field-row-tr">'
                '<td class="field-td f-name">' + fn + "</td>"
                '<td class="field-td f-op">' + op + "</td>"
                '<td class="field-td">' + fmt_val(val) + "</td>" + snip_td + "</tr>"
            )

        qp_html = (
            '<div class="ev-qpart"><b>slice ·</b> ' + qpart + "</div>" if qpart else ""
        )

        html += (
            '<div class="ev-card">'
            '<div class="ev-name">⬡ ' + name + "</div>"
            '<table class="field-table">' + rows + "</table>" + qp_html + "</div>"
        )
    return html


def render_attribute_conditions(attr_conditions: dict) -> str:
    """Render attribute_conditions block as a styled card."""
    if not attr_conditions:
        return ""

    # FIX 1: guard None conditionType — use "—" as display fallback
    condition_type = attr_conditions.get("conditionType") or "—"
    conditions = attr_conditions.get("conditions", [])

    rows = ""
    for c in conditions:
        key = c.get("key", "")
        operator = c.get("operator", "")
        value = c.get("value", "")
        raw_slice = c.get("raw_slice", "")

        raw_td = (
            '<td class="attr-cond-td ac-raw">"' + raw_slice + '"</td>'
            if raw_slice
            else '<td class="attr-cond-td"></td>'
        )

        rows += (
            '<tr class="attr-cond-row">'
            '<td class="attr-cond-td ac-key">' + key + "</td>"
            '<td class="attr-cond-td ac-op">' + operator + "</td>"
            '<td class="attr-cond-td ac-val">' + str(value) + "</td>" + raw_td + "</tr>"
        )

    empty_html = (
        '<div style="font-family:IBM Plex Mono,monospace;font-size:0.8rem;color:#8a9ab8;font-style:italic;">No conditions defined.</div>'
        if not rows
        else ""
    )

    return (
        '<div class="attr-cond-card">'
        '<div class="attr-cond-label">⧫ Attribute Conditions</div>'
        '<div class="attr-cond-type">condition type · '
        + condition_type
        + "</div>"
        + (
            '<table class="attr-cond-table">'
            "<thead><tr>"
            '<th style="font-family:IBM Plex Mono,monospace;font-size:0.6rem;letter-spacing:0.18em;text-transform:uppercase;color:#8a9ab8;font-weight:600;padding:0 0 0.5rem 0;text-align:left;border-bottom:1.5px solid #eaeff8;">key</th>'
            '<th style="font-family:IBM Plex Mono,monospace;font-size:0.6rem;letter-spacing:0.18em;text-transform:uppercase;color:#8a9ab8;font-weight:600;padding:0 0 0.5rem 0;text-align:left;border-bottom:1.5px solid #eaeff8;">operator</th>'
            '<th style="font-family:IBM Plex Mono,monospace;font-size:0.6rem;letter-spacing:0.18em;text-transform:uppercase;color:#8a9ab8;font-weight:600;padding:0 0 0.5rem 0;text-align:left;border-bottom:1.5px solid #eaeff8;">value</th>'
            '<th style="font-family:IBM Plex Mono,monospace;font-size:0.6rem;letter-spacing:0.18em;text-transform:uppercase;color:#8a9ab8;font-weight:600;padding:0 0 0.5rem 0;text-align:left;border-bottom:1.5px solid #eaeff8;">raw slice</th>'
            "</tr></thead>"
            "<tbody>" + rows + "</tbody>"
            "</table>"
            if rows
            else empty_html
        )
        + "</div>"
    )


def render_video_groups(groups: list) -> str:
    badge_colors = {
        "ip": ("#8a2be2", "#f0e8ff"),
        "exact": ("#16803a", "#e8faf0"),
        "partial": ("#1a5cf0", "#eaf0ff"),
        "fuzzy": ("#5a6a88", "#eef1f8"),
    }

    html = (
        '<div class="card card-accent"><div class="card-label">📹 Video Resources</div>'
    )

    if not groups:
        html += '<div class="vgroup-empty">No cameras resolved.</div>'
    else:
        for group in groups:
            token = group.get("matched_token", "")
            raw = group.get("matched_raw_slice", "")
            mtype = group.get("match_type", "")
            conf = group.get("confidence", "")
            cameras = group.get("cameras", [])

            fc, bc = badge_colors.get(mtype, ("#5a6a88", "#eef1f8"))
            badge_style = f"color:{fc};background:{bc};border:1px solid {fc}40;"

            info_rows = (
                '<div class="vgroup-info-row">'
                '<div class="vgroup-info-key">matched token</div>'
                '<div class="vgroup-info-val token">' + token + "</div>"
                "</div>"
                '<div class="vgroup-info-row">'
                '<div class="vgroup-info-key">raw slice</div>'
                '<div class="vgroup-info-val slice">' + raw + "</div>"
                "</div>"
            )

            chips = "".join('<span class="cam-chip">' + c + "</span>" for c in cameras)

            html += (
                '<div class="vgroup">'
                '<div class="vgroup-header">'
                '<span class="vgroup-name">' + token + "</span>"
                '<span class="vgroup-badge" style="'
                + badge_style
                + '">'
                + mtype
                + " · "
                + str(conf)
                + "%"
                "</span>"
                "</div>"
                '<div class="vgroup-info">' + info_rows + "</div>"
                '<div class="cam-wrap">' + chips + "</div>"
                "</div>"
            )

    html += "</div>"
    return html


# ─────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────
st.markdown(
    """
<div class="hero">
    <div class="hero-eyebrow">Natural Language Intelligence</div>
    <div class="hero-title">Query <span>Pipeline</span></div>
    <div class="hero-desc">Parse natural language into structured event filters, time ranges, and camera resources.</div>
</div>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# Input
# ─────────────────────────────────────────────
query = st.text_area(
    "query",
    value="Fetch events for last 7 days from ip source 192.168.9 for wanted person named Karan Desai showing angry emotion was seen riding stolen red bike with plate number HR5653RT78 violating traffic signal and speed limit, also check if his address is mg road, gurugram.",
    height=110,
    label_visibility="collapsed",
)
_, btn_col, _ = st.columns([2, 1, 2])
with btn_col:
    run = st.button("Analyze Query")

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Call API & Render
# ─────────────────────────────────────────────
if run and query.strip():
    with st.spinner("Running pipeline…"):
        try:
            resp = requests.post(API_URL, json={"query": query}, timeout=180)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            st.error(f"API error: {e}")
            st.stop()

    status = data.get("status", "success")
    sa = data.get("source_attributions", {})

    if status == "irrelevant":
        msg = data.get("message") or "No relevant events found."
        st.markdown(
            '<div class="status-irr">irrelevant · ' + msg + "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="status-ok">pipeline complete · ' + status + "</div>",
            unsafe_allow_html=True,
        )

    # Query echo
    st.markdown(
        '<div class="card" style="margin-bottom:1.8rem;">'
        '<div class="card-label">◈ Query</div>'
        '<div style="font-size:1rem; color:#2a3a5a; line-height:1.7; font-weight:500;">'
        + data.get("query", "")
        + "</div></div>",
        unsafe_allow_html=True,
    )

    # ── ROW 1: Time | Video | Attribute Conditions ──────────────
    col_time, col_video, col_attr = st.columns([1, 1, 1], gap="large")

    # TIME
    with col_time:
        time_data = data.get("time", {}) or {}
        # FIX 2: guard None time_attr with fallback to empty dict
        time_attr = sa.get("time") or {}
        start = time_data.get("start", {}) or {}
        end = time_data.get("end", {}) or {}
        st.markdown(
            f"""
        <div class="card card-accent">
            <div class="card-label">⏱ Time Range</div>
            <div class="time-grid">
                <div class="time-cell">
                    <div class="time-cell-label">Start</div>
                    <div class="time-cell-date">{start.get("date", "—")}</div>
                    <div class="time-cell-time">{start.get("time", "")}</div>
                </div>
                <div class="time-cell">
                    <div class="time-cell-label">End</div>
                    <div class="time-cell-date">{end.get("date", "—")}</div>
                    <div class="time-cell-time">{end.get("time", "")}</div>
                </div>
            </div>
            <div class="time-meta">
                <div class="time-meta-item">intent · <span>{time_attr.get("time_intent", "—")}</span></div>
                <div class="time-meta-item">subclass · <span>{time_attr.get("intent_subclass", "—")}</span></div>
                <div class="time-meta-item">phrase · <span>"{time_attr.get("raw_time_query", "—")}"</span></div>
            </div>
        </div>""",
            unsafe_allow_html=True,
        )

    # VIDEO
    with col_video:
        groups = data.get("video_resources", {}).get("groups", [])
        st.markdown(render_video_groups(groups), unsafe_allow_html=True)

    # ATTRIBUTE CONDITIONS
    with col_attr:
        attr_conditions = data.get("attribute_conditions", {})
        if attr_conditions:
            st.markdown(
                render_attribute_conditions(attr_conditions), unsafe_allow_html=True
            )

    # ── ROW 2: Extracted Event Fields (full width) ────────────
    st.markdown("<br>", unsafe_allow_html=True)
    extracted = data.get("extracted_fields", [])
    field_attrs = sa.get("fields") or {}
    if extracted:
        events_html = render_events(extracted, field_attrs)
        st.markdown(
            '<div class="events-row-card">'
            '<div class="card-label">⬡ Extracted Event Fields</div>'
            '<div class="events-inner-grid">' + events_html + "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Raw JSON ─────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("Raw Response"):
        st.code(json.dumps(data, indent=2), language="json")

elif run:
    st.warning("Please enter a query.")
