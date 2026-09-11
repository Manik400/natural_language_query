import glob
import json
import os
import shutil
import tempfile
from copy import deepcopy

import streamlit as st

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA_DIR = os.path.join(BASE_DIR, "artifacts", "events_schema")
INPUT_FILE = os.path.join(BASE_DIR, "evaluate", "data", "fields", "response.jsonl")
OUTPUT_FILE = os.path.join(BASE_DIR, "evaluate", "data", "fields", "annotated.jsonl")

st.set_page_config(page_title="Field Annotation Tool", layout="wide")

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


# ── Schemas ──────────────────────────────────────────────────────────────────
@st.cache_data
def load_event_schemas():
    schemas = {}
    for filepath in sorted(glob.glob(os.path.join(SCHEMA_DIR, "*.json"))):
        with open(filepath, "r", encoding="utf-8") as f:
            schema = json.load(f)
        event_name = schema["title"]
        schemas[event_name] = schema
    return schemas


def get_field_config(schema):
    fields = {}
    for field_name, field_config in schema.get("properties", {}).items():
        info = {
            "type": field_config.get("type", "string"),
            "description": field_config.get("description", ""),
        }
        for key in ["enum", "minimum", "maximum", "default"]:
            if key in field_config:
                info[key] = field_config[key]
        fields[field_name] = info
    return fields


OPERATOR_OPTIONS = [
    "Equal",
    "NotEqual",
    "GreaterThan",
    "LessThan",
    "GreaterThanOrEqual",
    "LessThanOrEqual",
    "Contains",
    "NotContains",
]


# ── JSONL I/O ────────────────────────────────────────────────────────────────
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


# ── Dataset ───────────────────────────────────────────────────────────────────
def load_annotation_dataset():
    source_items = load_jsonl(INPUT_FILE)

    saved_map = {
        item.get("query", "").strip(): item for item in load_jsonl(OUTPUT_FILE)
    }

    merged = []
    for item in source_items:
        query = item.get("query", "").strip()
        original = deepcopy(item.get("response", {}))

        saved_item = saved_map.get(query, {})

        corrected = deepcopy(saved_item.get("corrected_response", original))

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


# ── Field widget ──────────────────────────────────────────────────────────────
def field_widget(field_config, current_value, key):
    if "enum" in field_config:
        opts = [""] + [str(o) for o in field_config["enum"]]
        str_val = str(current_value) if current_value is not None else ""
        sel = str_val if str_val in opts else ""
        chosen = st.selectbox("Value", opts, index=opts.index(sel), key=key)

        for e in field_config["enum"]:
            if str(e) == chosen:
                return e
        return chosen

    t = field_config["type"]

    if t == "boolean":
        if isinstance(current_value, str):
            val = current_value.lower() == "true"
        else:
            val = bool(current_value) if current_value is not None else False
        return st.checkbox("Value", value=val, key=key)

    if t == "integer":
        try:
            val = int(current_value) if current_value is not None else 0
        except (ValueError, TypeError):
            val = 0

        return st.number_input(
            "Value",
            value=val,
            min_value=int(field_config.get("minimum", 0)),
            step=1,
            key=key,
        )

    if t == "number":
        try:
            val = float(current_value) if current_value is not None else 0.0
        except (ValueError, TypeError):
            val = 0.0

        return st.number_input(
            "Value",
            value=val,
            min_value=float(field_config.get("minimum", 0.0)),
            key=key,
        )

    return st.text_input(
        "Value",
        value=str(current_value) if current_value is not None else "",
        key=key,
    )


# ── Bootstrap session state ───────────────────────────────────────────────────
schemas = load_event_schemas()

if "annotations" not in st.session_state:
    st.session_state.annotations = load_annotation_dataset()

if "current_index" not in st.session_state:
    st.session_state.current_index = 0


# ── UI ────────────────────────────────────────────────────────────────────────
st.title("Field Annotation Tool")

annotations = st.session_state.annotations
total = len(annotations)
reviewed = sum(
    1 for a in annotations if a.get("corrected_response") != a.get("original_response")
)

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


# ── Query ─────────────────────────────────────────────────────────────────────
st.subheader("Query")
st.markdown(
    f'<div class="query-box">{item["query"].replace("<", "&lt;").replace(">", "&gt;")}</div>',
    unsafe_allow_html=True,
)


# ── Live preview ──────────────────────────────────────────────────────────────
st.subheader("Corrected Response (Live)")
preview = [
    {
        "event_name": ev.get("event_name", ""),
        "query_part": ev.get("query_part", ""),
        "relevant_fields": ev.get("relevant_fields", []),
    }
    for ev in corrected
]
st.markdown(
    f'<div class="response-preview">{json.dumps(preview, indent=2, ensure_ascii=False)}</div>',
    unsafe_allow_html=True,
)
st.divider()


# ── Events ────────────────────────────────────────────────────────────────────
st.subheader("Events")

for i in range(len(corrected)):
    ev = corrected[i]
    current_name = ev.get("event_name", "")
    schema_key = current_name

    with st.expander(f"Event {i + 1}: {current_name or 'Unknown'}", expanded=True):
        col_type, col_del = st.columns([4, 1])

        with col_type:
            schema_keys = list(schemas.keys())
            cur_idx = schema_keys.index(schema_key) if schema_key in schema_keys else 0
            new_sk = st.selectbox(
                "Event Type",
                schema_keys,
                index=cur_idx,
                key=f"etype_{idx}_{i}",
            )

        with col_del:
            if st.button("✕ Remove", key=f"rm_{idx}_{i}"):
                corrected.pop(i)
                st.rerun()

        if new_sk != schema_key:
            ev["event_name"] = new_sk
            ev["relevant_fields"] = []

        ev.setdefault("query_part", "")
        ev["query_part"] = st.text_input(
            "query_part",
            value=ev["query_part"],
            placeholder="Part of the query that triggers this event",
            key=f"qp_{idx}_{i}",
        )

        st.markdown("---")

        fields_cfg = get_field_config(schemas[new_sk])
        ev.setdefault("relevant_fields", [])

        new_rf = []
        for j, rf in enumerate(ev["relevant_fields"]):
            fname = rf.get("field", "")
            fcfg = fields_cfg.get(fname, {"type": "string", "description": ""})

            col_hdr, col_rm = st.columns([6, 1])
            with col_hdr:
                st.markdown(f"**`{fname}`**")
                if fcfg.get("description"):
                    st.caption(fcfg["description"])

            with col_rm:
                if st.button("✕", key=f"rf_rm_{idx}_{i}_{j}"):
                    ev["relevant_fields"].pop(j)
                    st.rerun()

            vc, oc, sc = st.columns([3, 2, 3])

            with vc:
                new_val = field_widget(
                    fcfg,
                    rf.get("value"),
                    f"fv_{idx}_{i}_{fname}",
                )

            with oc:
                cur_op = rf.get("operator", "Equal")
                op_idx = (
                    OPERATOR_OPTIONS.index(cur_op) if cur_op in OPERATOR_OPTIONS else 0
                )
                new_op = st.selectbox(
                    "Operator",
                    OPERATOR_OPTIONS,
                    index=op_idx,
                    key=f"op_{idx}_{i}_{fname}",
                )

            with sc:
                new_snip = st.text_input(
                    "query_snippet",
                    value=rf.get("query_snippet", ""),
                    placeholder="Exact query text for this value",
                    key=f"fs_{idx}_{i}_{fname}",
                )

            new_rf.append(
                {
                    "field": fname,
                    "operator": new_op,
                    "value": new_val,
                    "query_snippet": new_snip,
                }
            )

            st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

        ev["relevant_fields"] = new_rf

        already_added = {rf["field"] for rf in ev["relevant_fields"]}
        available_fields = [f for f in fields_cfg if f not in already_added]

        if available_fields:
            af_col, ab_col = st.columns([4, 1])

            with af_col:
                add_field = st.selectbox(
                    "+ Add field",
                    [""] + available_fields,
                    key=f"add_field_sel_{idx}_{i}",
                )

            with ab_col:
                if add_field and st.button(
                    "+ Add",
                    key=f"add_field_btn_{idx}_{i}",
                ):
                    ev["relevant_fields"].append(
                        {
                            "field": add_field,
                            "operator": "Equal",
                            "value": None,
                            "query_snippet": "",
                        }
                    )
                    st.rerun()

st.divider()


# ── Add event ─────────────────────────────────────────────────────────────────
add_type = st.selectbox("Add New Event", [""] + list(schemas.keys()), key="add_ev")
if add_type and st.button(f"+ Add {add_type}"):
    corrected.append(
        {
            "event_name": add_type,
            "query_part": "",
            "relevant_fields": [],
        }
    )
    st.rerun()

st.divider()


# ── Save ──────────────────────────────────────────────────────────────────────
s1, s2, s3 = st.columns(3)

with s1:
    if st.button("💾 Save"):
        persist(idx, corrected)
        st.success("Saved successfully (atomic write).")

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
