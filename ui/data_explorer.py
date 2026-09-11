"""Data Explorer page: browse and filter the whole dummy event dataset."""

import html

import altair as alt
import pandas as pd
import streamlit as st

from ui.cache import cached_events, camera_names, events_frame

# Chart tokens — the app's own palette (brand blue on white cards, cool hairlines).
BLUE = "#1a5cf0"
INK_SECONDARY = "#5a6a88"
INK_MUTED = "#8a9ab8"
GRID = "#eaeff8"
AXIS = "#d0d8ea"
SURFACE = "#ffffff"
FONT = "Outfit, system-ui, -apple-system, 'Segoe UI', sans-serif"
SEARCH_COLUMNS = ["Event ID", "Event", "Camera", "IP", "Details", "Address"]


def styled(chart: alt.TopLevelMixin, height: int) -> alt.TopLevelMixin:
    return (
        chart.properties(height=height)
        .configure(font=FONT, background=SURFACE, padding={"left": 4, "right": 18, "top": 10, "bottom": 4})
        .configure_view(stroke=None)
        .configure_axis(
            labelColor=INK_MUTED, titleColor=INK_SECONDARY, gridColor=GRID, gridWidth=1,
            domainColor=AXIS, tickColor=AXIS, labelFontSize=11, labelPadding=6,
        )
    )


def daily_chart(daily: pd.DataFrame) -> alt.TopLevelMixin:
    base = alt.Chart(daily).encode(
        x=alt.X("Day:T", title=None, axis=alt.Axis(format="%d %b", labelAngle=0, tickCount=8, grid=False)),
    )
    y = alt.Y("Events:Q", title=None, axis=alt.Axis(tickCount=4, domain=False, ticks=False))
    hover = alt.selection_point(nearest=True, on="mouseover", clear="mouseout", fields=["Day"], empty=False)
    area = base.mark_area(color=BLUE, opacity=0.10).encode(y=y)
    line = base.mark_line(color=BLUE, strokeWidth=2, strokeJoin="round", strokeCap="round").encode(y="Events:Q")
    rule = base.mark_rule(color=AXIS, strokeWidth=1).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0))
    )
    dot = base.mark_point(filled=True, size=80, color=BLUE, stroke=SURFACE, strokeWidth=2).encode(
        y="Events:Q", opacity=alt.condition(hover, alt.value(1), alt.value(0))
    )
    catcher = base.mark_point(size=400, opacity=0).encode(
        y="Events:Q",
        tooltip=[alt.Tooltip("Day:T", title="Day", format="%a %d %b %Y"),
                 alt.Tooltip("Events:Q", title="Events", format=",")],
    ).add_params(hover)
    return styled(area + line + rule + dot + catcher, 240)


def bar_chart(counts: pd.DataFrame, label: str) -> alt.TopLevelMixin:
    base = alt.Chart(counts).encode(
        y=alt.Y(f"{label}:N", sort="-x", title=None,
                axis=alt.Axis(ticks=False, domain=False, labelLimit=220, labelColor=INK_SECONDARY)),
        x=alt.X("Events:Q", title=None,
                axis=alt.Axis(labels=False, ticks=False, domain=False, grid=True, tickCount=4)),
        tooltip=[alt.Tooltip(f"{label}:N"), alt.Tooltip("Events:Q", format=",")],
    )
    bars = base.mark_bar(color=BLUE, cornerRadiusEnd=4, size=14)
    labels = base.mark_text(align="left", dx=6, color=INK_SECONDARY, fontSize=11).encode(
        text=alt.Text("Events:Q", format=",")
    )
    return styled(bars + labels, max(160, 26 * len(counts)))


def stat_tile(label: str, value: str, note: str = "", hero: bool = False) -> str:
    cls = "stat-tile hero" if hero else "stat-tile"
    note_html = f'<div class="stat-note">{html.escape(note)}</div>' if note else ""
    return (f'<div class="{cls}"><div class="stat-label">{html.escape(label)}</div>'
            f'<div class="stat-value">{html.escape(value)}</div>{note_html}</div>')


# ─────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────
events = cached_events()
events_by_id = {e["event_id"]: e for e in events}
df_all = events_frame(events)
df_all["Day"] = df_all["Time"].dt.normalize()
first_day, last_day = df_all["Day"].min().date(), df_all["Day"].max().date()
all_cameras = camera_names()
all_types = sorted(df_all["Event"].unique())

st.markdown(
    f"""
<div class="hero">
    <div class="hero-eyebrow">Demo dataset</div>
    <div class="hero-title">Data <span>Explorer</span></div>
    <div class="hero-desc">{len(df_all):,} synthetic surveillance events across {len(all_types)} analytics and
    {len(all_cameras)} cameras. Dates are shifted so the data always runs up to today.</div>
</div>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# Filters (one row, above everything they affect)
# ─────────────────────────────────────────────
c_date, c_type, c_cam, c_text = st.columns([1.3, 1.6, 1.6, 1.4])
with c_date:
    picked = st.date_input("Date range", value=(first_day, last_day), min_value=first_day,
                           max_value=last_day, format="DD/MM/YYYY")
with c_type:
    types = st.multiselect("Analytics", all_types, placeholder="All analytics")
with c_cam:
    cams = st.multiselect("Cameras", all_cameras, placeholder="All cameras")
with c_text:
    text = st.text_input("Search", placeholder="Plate, name, address…")

start_day, end_day = (picked if isinstance(picked, tuple) and len(picked) == 2
                      else ((picked[0], picked[0]) if isinstance(picked, tuple) and picked else (first_day, last_day)))
mask = (df_all["Day"].dt.date >= start_day) & (df_all["Day"].dt.date <= end_day)
if types:
    mask &= df_all["Event"].isin(types)
if cams:
    mask &= df_all["Camera"].isin(cams)
if text.strip():
    needle = text.strip()
    mask &= df_all[SEARCH_COLUMNS].apply(lambda col: col.str.contains(needle, case=False, regex=False)).any(axis=1)
df = df_all[mask]

if df.empty:
    st.info("No events match these filters.")
    st.stop()

# ─────────────────────────────────────────────
# Stat tiles
# ─────────────────────────────────────────────
days_in_view = (end_day - start_day).days + 1
per_day = df.groupby("Day").size()
busiest = per_day.idxmax()
st.markdown(
    '<div class="stat-grid">'
    + stat_tile("Events in view", f"{len(df):,}", f"{start_day:%d %b} – {end_day:%d %b %Y}", hero=True)
    + stat_tile("Cameras reporting", f"{df['Camera'].nunique()}", f"of {len(all_cameras)} cameras")
    + stat_tile("Analytics", f"{df['Event'].nunique()}", f"of {len(all_types)} event types")
    + stat_tile("Busiest day", f"{per_day.max():,}", f"{busiest:%a %d %b} · avg {len(df) / days_in_view:.0f}/day")
    + "</div>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────
days = pd.date_range(start_day, end_day, freq="D")
daily = per_day.reindex(days, fill_value=0).rename_axis("Day").reset_index(name="Events")
with st.container(border=True):
    st.markdown('<div class="card-label">Events per day</div>', unsafe_allow_html=True)
    st.altair_chart(daily_chart(daily), theme=None, width="stretch")

left, right = st.columns(2, gap="medium")
with left, st.container(border=True):
    st.markdown('<div class="card-label">Events by analytics</div>', unsafe_allow_html=True)
    by_type = df["Event"].value_counts().rename_axis("Analytics").reset_index(name="Events")
    st.altair_chart(bar_chart(by_type, "Analytics"), theme=None, width="stretch")
with right, st.container(border=True):
    st.markdown('<div class="card-label">Top 10 cameras</div>', unsafe_allow_html=True)
    by_cam = df["Camera"].value_counts().head(10).rename_axis("Camera").reset_index(name="Events")
    st.altair_chart(bar_chart(by_cam, "Camera"), theme=None, width="stretch")

# ─────────────────────────────────────────────
# Table + record detail
# ─────────────────────────────────────────────
table = df.drop(columns=["Day"])
st.markdown(
    f'<div class="card-label" style="margin-top:1.2rem;">▤ Events · {len(table):,} rows · '
    "select a row to see its full record</div>",
    unsafe_allow_html=True,
)
selection = st.dataframe(
    table,
    hide_index=True,
    height=440,
    on_select="rerun",
    selection_mode="single-row",
    key="explorer_table",
    column_config={
        "Time": st.column_config.DatetimeColumn("Time", format="DD MMM YYYY, HH:mm"),
        "Details": st.column_config.TextColumn("Details", width="large"),
    },
)

rows = selection.selection.rows if selection else []
if rows:
    record = dict(events_by_id[table.iloc[rows[0]]["Event ID"]])
    record.pop("ts", None)
    with st.container(border=True):
        st.markdown(f'<div class="card-label">Record · {html.escape(record["event_id"])}</div>',
                    unsafe_allow_html=True)
        st.json(record)

act_left, act_right = st.columns([1, 1])
with act_left:
    st.download_button("Download filtered CSV", table.to_csv(index=False).encode("utf-8"),
                       file_name="dummy_events.csv", mime="text/csv", icon=":material/download:")
with act_right:
    st.page_link("ui/search_page.py", label="Ask this data a question in plain English",
                 icon=":material/search:")
