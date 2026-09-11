import json
import os
import shutil
import tempfile
from copy import deepcopy

import streamlit as st

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA_DIR = os.path.join(BASE_DIR, "artifacts", "events_schema")
INPUT_FILE = os.path.join(BASE_DIR, "evaluate", "data", "events", "response.jsonl")
OUTPUT_FILE = os.path.join(BASE_DIR, "evaluate", "data", "events", "annotated.jsonl")


st.markdown(
    """
<style>
.query-box {
  background: #f8f9fa;
  border-left: 4px solid #4a90e2;
  padding: 12px 16px;
  border-radius: 4px;
  font-size: 0.95rem;
  white-space: pre-wrap;
  word-break: break-word;
  color: #1a1a1a;
  margin-bottom: 8px;
}
.response-preview {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 14px 16px;
  border-radius: 6px;
  font-size: 0.82rem;
  font-family: 'Courier New', monospace;
  overflow-x: auto;
  white-space: pre;
  max-height: 420px;
  overflow-y: auto;
  margin-bottom: 8px;
}
</style>
""",
    unsafe_allow_html=True,
)


def load_jsonl(path):
    data = []
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def atomic_save_jsonl(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=os.path.dirname(path),
            prefix=os.path.basename(path) + ".",
            suffix=".tmp",
            delete=False,
        ) as f:
            tmp_path = f.name

            for item in data:
                record = {
                    "query": item["query"],
                    "corrected_response": item["corrected_response"],
                    "reviewed": item.get("reviewed", False),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            f.flush()
            os.fsync(f.fileno())

        shutil.move(tmp_path, path)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@st.cache_data
def discover_event_types():
    event_types = set()

    if not os.path.exists(SCHEMA_DIR):
        return []

    for filename in os.listdir(SCHEMA_DIR):
        if not filename.endswith(".json"):
            continue

        file_path = os.path.join(SCHEMA_DIR, filename)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                schema = json.load(f)

            title = schema.get("title")
            if title:
                event_types.add(title)

        except Exception as e:
            st.warning(f"Could not load {filename}: {e}")

    return sorted(event_types)


def normalize_response(response):
    if not isinstance(response, dict):
        response = {"status": "success", "matched_events": []}

    response.setdefault("status", "success")
    response.setdefault("matched_events", [])

    if not isinstance(response["matched_events"], list):
        response["matched_events"] = []

    return response


def load_annotation_dataset():
    source_items = load_jsonl(INPUT_FILE)

    saved_map = {
        item.get("query", "").strip(): item for item in load_jsonl(OUTPUT_FILE)
    }

    merged = []
    for item in source_items:
        query = item.get("query", "").strip()
        original = normalize_response(deepcopy(item.get("response", {})))

        saved_item = saved_map.get(query, {})

        corrected = normalize_response(
            deepcopy(saved_item.get("corrected_response", original))
        )

        merged.append(
            {
                "query": query,
                "original_response": deepcopy(original),
                "corrected_response": corrected,
                "reviewed": saved_item.get("reviewed", False),
            }
        )

    return merged


def persist(dataset_idx, corrected):
    st.session_state.annotations[dataset_idx]["corrected_response"] = deepcopy(
        corrected
    )
    st.session_state.annotations[dataset_idx]["reviewed"] = True
    atomic_save_jsonl(OUTPUT_FILE, st.session_state.annotations)


EVENT_TYPES = discover_event_types()

if "annotations" not in st.session_state:
    st.session_state.annotations = load_annotation_dataset()

if "current_index" not in st.session_state:
    st.session_state.current_index = 0


st.title("Event Matching Annotation Tool")

annotations = st.session_state.annotations
total = len(annotations)
reviewed = sum(1 for a in annotations if a.get("reviewed", False))

c1, c2, c3 = st.columns(3)
c1.metric("Total", total)
c2.metric("Edited", reviewed)
c3.metric("Remaining", total - reviewed)

st.divider()

if total == 0:
    st.warning("No data found in the input file.")
    st.stop()

idx = st.session_state.current_index
item = annotations[idx]

nav1, _, nav3 = st.columns([1, 3, 1])
with nav1:
    if st.button("⬅ Prev", disabled=idx == 0):
        st.session_state.current_index -= 1
        st.rerun()

with nav3:
    if st.button("Next ➡", disabled=idx >= total - 1):
        st.session_state.current_index += 1
        st.rerun()

jump_col, _ = st.columns([1, 4])
with jump_col:
    jump_to = st.number_input(
        "Jump to index",
        min_value=1,
        max_value=total,
        value=idx + 1,
        step=1,
        key="jump_input",
    )
    if st.button("Go", key="jump_btn"):
        st.session_state.current_index = int(jump_to) - 1
        st.rerun()

st.markdown(f"### Item {idx + 1} / {total}")

session_key = f"corrected_{idx}"
if session_key not in st.session_state:
    st.session_state[session_key] = deepcopy(item["corrected_response"])

corrected = st.session_state[session_key]
corrected = normalize_response(corrected)

st.subheader("Query")
st.markdown(
    f'<div class="query-box">{item["query"].replace("<", "&lt;").replace(">", "&gt;")}</div>',
    unsafe_allow_html=True,
)

st.subheader("Corrected Response (live)")
st.markdown(
    f'<div class="response-preview">{json.dumps(corrected, indent=2, ensure_ascii=False)}</div>',
    unsafe_allow_html=True,
)

st.divider()
st.subheader("Matched Events")

matched_events = corrected.setdefault("matched_events", [])

for i in range(len(matched_events)):
    event = matched_events[i]

    with st.expander(
        f"Event {i + 1}: {event.get('event_name', 'Unknown Event')}",
        expanded=True,
    ):
        col1, col2 = st.columns([4, 1])

        with col1:
            current_event = event.get("event_name", "")
            if current_event in EVENT_TYPES:
                default_idx = EVENT_TYPES.index(current_event)
            else:
                default_idx = 0 if EVENT_TYPES else None

            if EVENT_TYPES:
                event["event_name"] = st.selectbox(
                    "Event Name",
                    EVENT_TYPES,
                    index=default_idx,
                    key=f"event_name_{idx}_{i}",
                )
            else:
                event["event_name"] = st.text_input(
                    "Event Name",
                    value=current_event,
                    key=f"event_name_text_{idx}_{i}",
                )

        with col2:
            st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
            if st.button("✕ Remove", key=f"remove_event_{idx}_{i}"):
                matched_events.pop(i)
                st.rerun()

        event["query_part"] = st.text_area(
            "Query Part",
            value=event.get("query_part", ""),
            placeholder="Portion of the query that triggered this event",
            key=f"query_part_{idx}_{i}",
            height=100,
        )

st.divider()

if EVENT_TYPES:
    add_event_type = st.selectbox(
        "Add New Event", [""] + EVENT_TYPES, key=f"add_event_{idx}"
    )
else:
    add_event_type = st.text_input("Add New Event Type", key=f"add_event_text_{idx}")

if add_event_type and st.button("+ Add Event"):
    matched_events.append(
        {
            "event_name": add_event_type,
            "query_part": "",
        }
    )
    st.rerun()

st.divider()

s1, s2, s3 = st.columns(3)

with s1:
    if st.button("💾 Save"):
        persist(idx, corrected)
        st.success("Saved successfully.")

with s2:
    if st.button("💾 Save & Next"):
        persist(idx, corrected)
        if idx < total - 1:
            st.session_state.current_index += 1
        st.rerun()

with s3:
    if st.button("⏭ Skip"):
        if idx < total - 1:
            st.session_state.current_index += 1
        st.rerun()
