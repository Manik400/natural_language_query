"""Search page: plain-English query → parsed filters → matching dummy events."""

import html
import json

import streamlit as st

from demo.engine import MODE_AI, MODE_RULES, ai_available, parse_query
from demo.search_engine import search_events
from ui.cache import cached_events, events_frame

DEFAULT_QUERY = (
    "Fetch events for last 7 days from ip source 192.168.9 for wanted person named "
    "Karan Desai showing angry emotion was seen riding stolen red bike with plate number "
    "HR5653RT78 violating traffic signal and speed limit, also check if his address is "
    "mg road, gurugram."
)
EXAMPLES = {
    "Stolen red bike": DEFAULT_QUERY,
    "Missing PPE": "Workers without helmet or safety vest in the last 7 days",
    "Big crowds": "Crowd of more than 50 people in zone 3 in the past 30 days",
    "Red-light jumpers": "Cars travelling above 90 km/h that jumped the red light last week",
    "Masked visitors": "Female visitors wearing a mask in the past 30 days",
    "Reversing trucks": "Trucks reversing in the past 30 days",
}
ENGINE_LABELS = {MODE_RULES: "Offline rules", MODE_AI: "AI (LLM)"}


def esc(value) -> str:
    return html.escape(str(value))


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def fmt_val(v):
    if isinstance(v, bool):
        cls = "f-val f-val-t" if v else "f-val f-val-f"
        return f'<span class="{cls}">{"true" if v else "false"}</span>'
    if isinstance(v, (int, float)):
        return f'<span class="f-val f-val-n">{v}</span>'
    return f'<span class="f-val">{esc(v)}</span>'


def render_events(extracted_fields, field_attrs) -> str:
    """Return HTML string for all extracted event field cards."""
    html_out = ""
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
            snip = snips.get(fn, "")
            snip_td = (
                '<td class="field-td f-snip">"' + esc(snip) + '"</td>'
                if snip
                else '<td class="field-td"></td>'
            )
            rows += (
                '<tr class="field-row-tr">'
                '<td class="field-td f-name">' + esc(fn) + "</td>"
                '<td class="field-td f-op">' + esc(op) + "</td>"
                '<td class="field-td">' + fmt_val(f.get("value")) + "</td>" + snip_td + "</tr>"
            )
        if not rows:
            rows = '<tr><td class="field-td vgroup-empty">No field filters for this event.</td></tr>'

        qp_html = (
            '<div class="ev-qpart"><b>slice ·</b> ' + esc(qpart) + "</div>" if qpart else ""
        )
        html_out += (
            '<div class="ev-card">'
            '<div class="ev-name">⬡ ' + esc(name) + "</div>"
            '<table class="field-table">' + rows + "</table>" + qp_html + "</div>"
        )
    return html_out


def render_attribute_conditions(attr_conditions: dict) -> str:
    """Render attribute_conditions block as a styled card."""
    if not attr_conditions:
        return ""

    condition_type = attr_conditions.get("conditionType") or "—"
    th = (
        '<th style="font-family:IBM Plex Mono,monospace;font-size:0.6rem;letter-spacing:0.18em;'
        "text-transform:uppercase;color:#8a9ab8;font-weight:600;padding:0 0 0.5rem 0;"
        'text-align:left;border-bottom:1.5px solid #eaeff8;">{}</th>'
    )

    rows = ""
    for c in attr_conditions.get("conditions", []):
        raw_slice = c.get("raw_slice", "")
        raw_td = (
            '<td class="attr-cond-td ac-raw">"' + esc(raw_slice) + '"</td>'
            if raw_slice
            else '<td class="attr-cond-td"></td>'
        )
        rows += (
            '<tr class="attr-cond-row">'
            '<td class="attr-cond-td ac-key">' + esc(c.get("key", "")) + "</td>"
            '<td class="attr-cond-td ac-op">' + esc(c.get("operator", "")) + "</td>"
            '<td class="attr-cond-td ac-val">' + esc(c.get("value", "")) + "</td>" + raw_td + "</tr>"
        )

    body = (
        '<table class="attr-cond-table"><thead><tr>'
        + "".join(th.format(h) for h in ("key", "operator", "value", "raw slice"))
        + "</tr></thead><tbody>" + rows + "</tbody></table>"
        if rows
        else '<div class="vgroup-empty">No conditions defined.</div>'
    )
    return (
        '<div class="attr-cond-card">'
        '<div class="attr-cond-label">⧫ Attribute Conditions</div>'
        '<div class="attr-cond-type">condition type · ' + esc(condition_type) + "</div>"
        + body + "</div>"
    )


def render_video_groups(groups: list) -> str:
    badge_colors = {
        "ip": ("#8a2be2", "#f0e8ff"),
        "exact": ("#16803a", "#e8faf0"),
        "partial": ("#1a5cf0", "#eaf0ff"),
        "fuzzy": ("#5a6a88", "#eef1f8"),
    }
    html_out = '<div class="card card-accent"><div class="card-label">📹 Video Resources</div>'

    if not groups:
        html_out += '<div class="vgroup-empty">No cameras resolved — all cameras are searched.</div>'
    for group in groups:
        token = esc(group.get("matched_token", ""))
        raw = esc(group.get("matched_raw_slice", ""))
        mtype = group.get("match_type", "")
        fc, bc = badge_colors.get(mtype, ("#5a6a88", "#eef1f8"))
        chips = "".join('<span class="cam-chip">' + esc(c) + "</span>" for c in group.get("cameras", []))
        html_out += (
            '<div class="vgroup"><div class="vgroup-header">'
            '<span class="vgroup-name">' + token + "</span>"
            f'<span class="vgroup-badge" style="color:{fc};background:{bc};border:1px solid {fc}40;">'
            + esc(mtype) + " · " + esc(group.get("confidence", "")) + "%</span></div>"
            '<div class="vgroup-info">'
            '<div class="vgroup-info-row"><div class="vgroup-info-key">matched token</div>'
            '<div class="vgroup-info-val token">' + token + "</div></div>"
            '<div class="vgroup-info-row"><div class="vgroup-info-key">raw slice</div>'
            '<div class="vgroup-info-val slice">' + raw + "</div></div></div>"
            '<div class="cam-wrap">' + chips + "</div></div>"
        )
    return html_out + "</div>"


def render_time(data: dict, time_attr: dict) -> str:
    time_data = data.get("time") or {}
    start = time_data.get("start") or {}
    end = time_data.get("end") or {}
    return f"""
    <div class="card card-accent">
        <div class="card-label">⏱ Time Range</div>
        <div class="time-grid">
            <div class="time-cell">
                <div class="time-cell-label">Start</div>
                <div class="time-cell-date">{esc(start.get("date") or "—")}</div>
                <div class="time-cell-time">{esc(start.get("time") or "")}</div>
            </div>
            <div class="time-cell">
                <div class="time-cell-label">End</div>
                <div class="time-cell-date">{esc(end.get("date") or "—")}</div>
                <div class="time-cell-time">{esc(end.get("time") or "")}</div>
            </div>
        </div>
        <div class="time-meta">
            <div class="time-meta-item">intent · <span>{esc(time_attr.get("time_intent") or "—")}</span></div>
            <div class="time-meta-item">subclass · <span>{esc(time_attr.get("intent_subclass") or "—")}</span></div>
            <div class="time-meta-item">phrase · <span>"{esc(time_attr.get("raw_time_query") or "—")}"</span></div>
        </div>
    </div>"""


def render_matches(data: dict) -> None:
    result = search_events(cached_events(), data)
    if result["skipped"]:
        return

    matches = result["matches"]
    chips = "".join(
        f'<span class="filter-chip"><b>{esc(label)}</b>{esc(text)}</span>'
        for label, text in result["filters"]
    )
    st.markdown(
        '<div class="events-row-card">'
        '<div class="card-label">▤ Matching Events · dummy dataset</div>'
        f'<div class="result-count">{len(matches):,}</div>'
        f'<div class="result-sub">event{"s" if len(matches) != 1 else ""} match the filters parsed from your query</div>'
        f'<div class="filter-row">{chips}</div></div>',
        unsafe_allow_html=True,
    )
    if matches:
        st.dataframe(
            events_frame(matches),
            hide_index=True,
            height=min(440, 40 + 35 * len(matches)),
            column_config={
                "Time": st.column_config.DatetimeColumn("Time", format="DD MMM YYYY, HH:mm"),
                "Details": st.column_config.TextColumn("Details", width="large"),
            },
        )
    else:
        st.info("No dummy events match these filters. Try widening the time range or removing a condition.")
    st.page_link("ui/data_explorer.py", label="Browse the whole dataset", icon=":material/table_view:")


def _use_example():
    choice = st.session_state.get("example")
    if choice:
        st.session_state.query_text = EXAMPLES[choice]
        st.session_state.run_now = True


# ─────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────
st.markdown(
    """
<div class="hero">
    <div class="hero-eyebrow">Natural Language Intelligence</div>
    <div class="hero-title">Query <span>Pipeline</span></div>
    <div class="hero-desc">Parse natural language into structured event filters, time ranges, and camera resources — then search the demo dataset with them.</div>
</div>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# Input
# ─────────────────────────────────────────────
if "query_text" not in st.session_state:
    st.session_state.query_text = DEFAULT_QUERY

st.pills("Try an example", list(EXAMPLES), key="example", on_change=_use_example)
query = st.text_area("query", key="query_text", height=110, label_visibility="collapsed")

engine_col, btn_col, _ = st.columns([2, 1, 2], vertical_alignment="center")
with engine_col:
    if ai_available():
        mode = st.segmented_control(
            "Engine", [MODE_AI, MODE_RULES], default=MODE_AI,
            format_func=ENGINE_LABELS.get, label_visibility="collapsed",
        ) or MODE_AI
    else:
        mode = MODE_RULES
        st.markdown(
            '<div class="engine-note">Engine · <b>offline rules</b> (no AI key configured)</div>',
            unsafe_allow_html=True,
        )
with btn_col:
    run = st.button("Analyze Query")

run = run or st.session_state.pop("run_now", False)
st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Parse & Render
# ─────────────────────────────────────────────
if run and query.strip():
    with st.spinner("Running pipeline…"):
        try:
            st.session_state.last_result = parse_query(query, mode)
        except Exception as e:
            st.error(f"Pipeline error: {e}")
            st.stop()
elif run:
    st.warning("Please enter a query.")

data = st.session_state.get("last_result")
if data:
    status = data.get("status", "success")
    sa = data.get("source_attributions") or {}
    engine = ENGINE_LABELS.get(data.get("engine"), "")

    if status == "irrelevant":
        msg = data.get("message") or "No relevant events found."
        st.markdown(f'<div class="status-irr">irrelevant · {esc(msg)}</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div class="status-ok">pipeline complete · {esc(status)} · {esc(engine)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="card" style="margin-bottom:1.8rem;">'
        '<div class="card-label">◈ Query</div>'
        '<div style="font-size:1rem; color:#2a3a5a; line-height:1.7; font-weight:500;">'
        + esc(data.get("query", ""))
        + "</div></div>",
        unsafe_allow_html=True,
    )

    if status != "irrelevant":
        # ── ROW 1: Time | Video | Attribute Conditions ──────────────
        col_time, col_video, col_attr = st.columns([1, 1, 1], gap="large")
        with col_time:
            st.markdown(render_time(data, sa.get("time") or {}), unsafe_allow_html=True)
        with col_video:
            groups = (data.get("video_resources") or {}).get("groups", [])
            st.markdown(render_video_groups(groups), unsafe_allow_html=True)
        with col_attr:
            attr_conditions = data.get("attribute_conditions") or {}
            if attr_conditions:
                st.markdown(render_attribute_conditions(attr_conditions), unsafe_allow_html=True)

        # ── ROW 2: Extracted Event Fields (full width) ────────────
        st.markdown("<br>", unsafe_allow_html=True)
        extracted = data.get("extracted_fields", [])
        if extracted:
            events_html = render_events(extracted, sa.get("fields") or {})
            st.markdown(
                '<div class="events-row-card">'
                '<div class="card-label">⬡ Extracted Event Fields</div>'
                '<div class="events-inner-grid">' + events_html + "</div>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── ROW 3: Matching dummy events ───────────────────────────
        render_matches(data)

    # ── Raw JSON ─────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("Raw Response"):
        st.code(json.dumps(data, indent=2, default=str), language="json")
