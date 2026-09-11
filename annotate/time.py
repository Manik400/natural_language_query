import json
import os
import re
import shutil
import tempfile
from copy import deepcopy

import streamlit as st

from nodes.time.constants import ALLOWED_VALUES, INTENT_REGISTRY

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONSTANTS_FILE = os.path.join(BASE_DIR, "nodes", "time", "constants.py")
INPUT_FILE = os.path.join(BASE_DIR, "evaluate", "data", "time", "response.jsonl")
OUTPUT_FILE = os.path.join(BASE_DIR, "evaluate", "data", "time", "annotated.jsonl")

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3])([0-5]\d)([0-5]\d)$")

st.set_page_config(page_title="Time Intent Annotation Tool", layout="wide")

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
  color: #1a1a1a;
}
.response-preview {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 14px 16px;
  border-radius: 6px;
  font-size: 0.82rem;
  font-family: 'Courier New', monospace;
  white-space: pre;
  overflow-x: auto;
  max-height: 420px;
  overflow-y: auto;
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
                    "corrected_llm_response": item["corrected_llm_response"],
                    "reviewed": item.get("reviewed", False),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            f.flush()
            os.fsync(f.fileno())

        shutil.move(tmp_path, path)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def load_dataset():
    source_items = load_jsonl(INPUT_FILE)

    saved_map = {
        item.get("query", "").strip(): item for item in load_jsonl(OUTPUT_FILE)
    }

    merged = []
    for item in source_items:
        query = item.get("query", "").strip()
        llm_response = item.get("response", {}).get("llm_response", {})

        saved_item = saved_map.get(query, {})

        corrected = deepcopy(saved_item.get("corrected_llm_response", llm_response))

        merged.append(
            {
                "query": query,
                "original_llm_response": deepcopy(llm_response),
                "corrected_llm_response": corrected,
                "reviewed": saved_item.get("reviewed", False),
            }
        )

    return merged


def persist(dataset_idx, corrected):
    st.session_state.annotations[dataset_idx]["corrected_llm_response"] = deepcopy(
        corrected
    )
    st.session_state.annotations[dataset_idx]["reviewed"] = True
    atomic_save_jsonl(OUTPUT_FILE, st.session_state.annotations)


def get_subclasses(intent):
    return list(INTENT_REGISTRY.get(intent, {}).keys())


def get_required_optional(intent, subclass):
    cfg = INTENT_REGISTRY.get(intent, {}).get(subclass, {})
    return cfg.get("required", set()), cfg.get("optional", set())


def param_widget(param_name, current_value, key):
    allowed = ALLOWED_VALUES.get(param_name)

    if allowed:
        options = [""] + sorted(str(v) for v in allowed)
        current = str(current_value) if current_value is not None else ""
        index = options.index(current) if current in options else 0
        return st.selectbox(param_name, options, index=index, key=key)

    if param_name in {"raw_time_start", "raw_time_end"}:
        value = st.text_input(
            param_name,
            value="" if current_value is None else str(current_value),
            placeholder="HHMMSS",
            key=key,
        )

        if value and not TIME_PATTERN.fullmatch(value):
            st.error(f"{param_name} must be in HHMMSS format (e.g., 155449)")

        return value

    return st.text_input(
        param_name,
        value="" if current_value is None else str(current_value),
        key=key,
    )


if "annotations" not in st.session_state:
    st.session_state.annotations = load_dataset()

if "current_index" not in st.session_state:
    st.session_state.current_index = 0

annotations = st.session_state.annotations

st.title("Time Intent Annotation Tool")

if not annotations:
    st.warning("No data found.")
    st.stop()

idx = st.session_state.current_index
item = annotations[idx]

total = len(annotations)
reviewed = sum(1 for a in annotations if a.get("reviewed", False))

c1, c2, c3 = st.columns(3)
c1.metric("Total", total)
c2.metric("Reviewed", reviewed)
c3.metric("Remaining", total - reviewed)

st.divider()

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

session_key = f"time_corrected_{idx}"
if session_key not in st.session_state:
    st.session_state[session_key] = deepcopy(item["corrected_llm_response"])

corrected = st.session_state[session_key]

st.subheader("Query")
st.markdown(
    f'<div class="query-box">{item["query"].replace("<", "&lt;").replace(">", "&gt;")}</div>',
    unsafe_allow_html=True,
)

st.subheader("Corrected LLM Response (live)")
st.markdown(
    f'<div class="response-preview">{json.dumps(corrected, indent=2, ensure_ascii=False)}</div>',
    unsafe_allow_html=True,
)

st.divider()

corrected["raw_time_query"] = st.text_input(
    "raw_time_query",
    value=corrected.get("raw_time_query", ""),
)

intent_options = list(INTENT_REGISTRY.keys())
current_intent = corrected.get("timeIntent", intent_options[0])
intent_idx = (
    intent_options.index(current_intent) if current_intent in intent_options else 0
)
corrected["timeIntent"] = st.selectbox(
    "timeIntent",
    intent_options,
    index=intent_idx,
)

subclasses = get_subclasses(corrected["timeIntent"])
current_subclass = corrected.get(
    "timeIntentSubClass", subclasses[0] if subclasses else ""
)
sub_idx = subclasses.index(current_subclass) if current_subclass in subclasses else 0
corrected["timeIntentSubClass"] = st.selectbox(
    "timeIntentSubClass",
    subclasses,
    index=sub_idx if subclasses else 0,
)

required, optional = get_required_optional(
    corrected["timeIntent"],
    corrected["timeIntentSubClass"],
)

all_params = sorted(required | optional)
corrected.setdefault("params", {})
params = corrected["params"]

st.subheader("Parameters")

new_params = {}
for param in all_params:
    label = f"{param} {'(required)' if param in required else '(optional)'}"
    st.markdown(f"**{label}**")
    new_params[param] = param_widget(
        param,
        params.get(param),
        key=f"param_{idx}_{param}",
    )

corrected["params"] = new_params

st.divider()

s1, s2, s3 = st.columns(3)
with s1:
    if st.button("Save"):
        persist(idx, corrected)
        st.success("Saved.")
with s2:
    if st.button("Save & Next"):
        persist(idx, corrected)
        if idx < total - 1:
            st.session_state.current_index += 1
        st.rerun()
with s3:
    if st.button("Skip"):
        if idx < total - 1:
            st.session_state.current_index += 1
        st.rerun()
