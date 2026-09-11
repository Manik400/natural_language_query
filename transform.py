"""
Query JSON → API Payload Transformer
======================================
Transforms the NLP-parsed query JSON into the API request payload format.

Usage:
    python transform.py --input query.json

Or import and use programmatically:
    from transform import transform
    output = transform(query_json)
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from nodes.attributes.constants import AttributeValueType, Operators
from nodes.fields.constants import OPERATORS  # list: index = operator code

# ---------------------------------------------------------------------------
# OPERATOR MAP  (lowercase name → int code)
# Built dynamically from OPERATORS list so it stays in sync automatically.
# All keys stored lowercase; callers must do op_str.lower() at lookup time.
# ---------------------------------------------------------------------------

OPERATOR_MAP: dict[str, int] = {name.lower(): idx for idx, name in enumerate(OPERATORS)}


# ---------------------------------------------------------------------------
# CONDITION MAP  (lowercase conditionType → operator code)
# conditionType is a logical combiner, not a comparison operator.
# All keys stored lowercase; callers must do condition_type.lower() at lookup time.
# ---------------------------------------------------------------------------

CONDITION_MAP: dict[str, int] = {
    "all": int(Operators.ALL),
    "and": int(Operators.ALL),
    "any": int(Operators.ANY),
    "or": int(Operators.ANY),
}

# Default top-level operator when conditionType is None (no attribute conditions matched)
_DEFAULT_TOP_OPERATOR = int(Operators.ALL)
IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------


def to_epoch_ms(date_str: str, time_str: str) -> int:
    """Convert date + time strings (IST) to UTC epoch milliseconds.
    Accepts both 'YYYY-MM-DD' and 'DD-MM-YYYY' date formats.
    """
    combined = f"{date_str} {time_str}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            dt = datetime.strptime(combined, fmt)
            return int(dt.replace(tzinfo=IST).timestamp() * 1000)
        except ValueError:
            continue
    raise ValueError(
        f"to_epoch_ms: unrecognised date/time format '{combined}'. "
        f"Expected 'YYYY-MM-DD HH:MM:SS' or 'DD-MM-YYYY HH:MM:SS'."
    )


def _current_day_range_ms() -> tuple[int, int]:
    """Return (start_of_today_ms, now_ms) in IST as UTC epoch milliseconds.

    start_of_today : current date at 00:00:00 IST
    end (now)      : current date + current time IST
    """
    now_ist = datetime.now(IST)
    start_of_day_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(start_of_day_ist.timestamp() * 1000)
    end_ms = int(now_ist.timestamp() * 1000)
    return start_ms, end_ms


def build_camera_lookup() -> dict:
    """Load cameras from config.VIDEO_JSON_PATH and return a name→id dict.

    Expected file format:
    [
      {"name": "PAPA_JOHNS_ENTRY_CAM01", "type": "camera",
       "ip": "192.168.9.12", "id": "77a32339-022d-5ef7-b3ae-b4f8d24bd4ce"},
      ...
    ]
    """
    with open(config.VIDEO_JSON_PATH) as f:
        cameras = json.load(f)
    return {cam["name"]: cam["id"] for cam in cameras}


def build_attribute_lookup() -> dict:
    """Load attributes from config.ATTRIBUTES_JSON_PATH and return a key→valueType dict.

    Expected file format:
    [
      {"key": "aadhar",        "valueType": "string"},
      {"key": "bank_number",   "valueType": "string"},
      ...
    ]
    """
    with open(config.ATTRIBUTES_JSON_PATH) as f:
        attributes = json.load(f)
    return {attr["key"]: attr["valueType"] for attr in attributes}


def load_event_schema(analytics_key: str) -> dict:
    """Load the JSON schema for a given analytics key from config.SCHEMA_DIR.

    Schema files are expected to be named:  <analytics_key>_EventProperties.json
    e.g.  ANPR_EventProperties.json
          Face_Recognition_EventProperties.json
    """
    schema_path = Path(config.SCHEMA_DIR) / f"{analytics_key}_EventProperties.json"
    if not schema_path.exists():
        return {}
    with open(schema_path) as f:
        return json.load(f)


def get_rule_type(analytics_key: str, field: str) -> int:
    """Return the ruleType int for a field by reading its event schema.

    Falls back to 1 (string) if schema or field is not found.
    """
    schema = load_event_schema(analytics_key)
    properties = schema.get("properties", {})
    field_def = properties.get(field, {})
    return field_def.get("ruleType", 1)  # default → 1 (string)


# ---------------------------------------------------------------------------
# CORE TRANSFORM
# ---------------------------------------------------------------------------


def transform(query_json: dict) -> dict:
    """
    Parameters
    ----------
    query_json : Parsed NLP query JSON (the full document from the AI pipeline).

    Returns
    -------
    dict : API payload ready for JSON serialisation.

    Special case
    ------------
    When query_json contains ``"status": "irrelevant"``, the pipeline found no
    relevant events.  The function short-circuits and returns a default payload
    with empty video sources, analytics, and filters, using today's date range
    (00:00:00 IST → now IST) as the time window.  The ``request_id`` from the
    input is forwarded as-is.
    """

    # ------------------------------------------------------------------
    # EARLY RETURN — irrelevant query
    # ------------------------------------------------------------------
    if query_json.get("status") == "irrelevant":
        start_ms, end_ms = _current_day_range_ms()
        return {
            "startTime": start_ms,
            "endTime": end_ms,
            "pageNumber": 1,
            "pageLimit": 50,
            "order": "DESC",
            "resources": {
                "Video_Sources": [],
            },
            "analytics": [],
            "propertyFilters": {},
            "AttributeFilters": None,
            "request_id": query_json.get("request_id"),
        }

    # ------------------------------------------------------------------
    # Normal path
    # ------------------------------------------------------------------
    camera_lookup = build_camera_lookup()
    attribute_lookup = build_attribute_lookup()

    # ------------------------------------------------------------------
    # 1. TIME
    # ------------------------------------------------------------------
    time_block = query_json["time"]
    start_ms = to_epoch_ms(time_block["start"]["date"], time_block["start"]["time"])
    end_ms = to_epoch_ms(time_block["end"]["date"], time_block["end"]["time"])

    # ------------------------------------------------------------------
    # 2. VIDEO SOURCES  (camera name → UUID)
    # ------------------------------------------------------------------
    resolved_cameras = query_json["video_resources"]["resolved_cameras"]
    video_sources = [camera_lookup[name] for name in resolved_cameras]

    # ------------------------------------------------------------------
    # 3. ANALYTICS  (event_name → analytics key)
    #    Strip trailing " Properties" suffix only, then replace spaces.
    #    Returns [] when extracted_fields is empty.
    # ------------------------------------------------------------------
    def event_to_analytics_key(event_name: str) -> str:
        suffix = " Properties"
        key = event_name[: -len(suffix)] if event_name.endswith(suffix) else event_name
        return key.strip().replace(" ", "_")

    extracted_fields = query_json["extracted_fields"]
    analytics = (
        [event_to_analytics_key(ef["event_name"]) for ef in extracted_fields]
        if extracted_fields
        else []
    )

    # ------------------------------------------------------------------
    # 4. PROPERTY FILTERS
    #    operator → OPERATOR_MAP via op_str.lower()
    #    ruleType → event schema JSON (config.SCHEMA_DIR)
    #    Returns {} when extracted_fields is empty or no rules are built.
    # ------------------------------------------------------------------
    property_filters = {}

    for ef in extracted_fields:
        analytics_key = event_to_analytics_key(ef["event_name"])
        rules = []

        for rf in ef["relevant_fields"]:
            field = rf["field"]
            op_str = rf["operator"]
            value = rf["value"]

            ruletype = get_rule_type(analytics_key, field)

            rules.append(
                {
                    "field": field,
                    "operator": OPERATOR_MAP[op_str.lower()],
                    "value": value,
                    "type": ruletype,
                    "rules": [],
                }
            )

        if rules:  # only add key when at least one rule was built
            property_filters[analytics_key] = {
                "condition": "AND",
                "rules": rules,
            }

    # ------------------------------------------------------------------
    # 5. ATTRIBUTE FILTERS
    #    attribute_conditions is always present in the pipeline output.
    #    conditionType may be None when no attribute conditions matched —
    #    guard only that field before the CONDITION_MAP lookup.
    #
    #    top operator → CONDITION_MAP via condition_type.lower()
    #                   falls back to _DEFAULT_TOP_OPERATOR when None
    #    valueType    → AttributeValueType enum
    #    condition    → Operators enum via op_str.upper() (enum key lookup)
    # ------------------------------------------------------------------
    attr_conditions = query_json["attribute_conditions"]
    condition_type = attr_conditions["conditionType"]  # present, but may be None
    conditions = attr_conditions["conditions"]  # always a valid list

    top_operator = (
        CONDITION_MAP[condition_type.lower()]
        if condition_type
        else _DEFAULT_TOP_OPERATOR
    )

    inner_rules = []
    for cond in conditions:
        key = cond["key"]
        op_str = cond["operator"]
        value = cond["value"]

        # Resolve valueType: prefer attribute_lookup, fall back to cond itself
        raw_vtype = attribute_lookup.get(key) or cond.get("valueType", "string")
        vtype_code = int(AttributeValueType[raw_vtype])  # e.g. "string" → 0

        inner_rules.append(
            {
                "key": key,
                "valueType": vtype_code,
                "condition": int(
                    Operators[op_str.upper()]
                ),  # enum key lookup → stays .upper()
                "value": value,
            }
        )

    attribute_filters = (
        {
            "field": "attributes",
            "operator": top_operator,
            "rules": [],
            "type": 21,
            "value": json.dumps(inner_rules, separators=(",", ":")),
        }
        if inner_rules
        else None
    )

    # ------------------------------------------------------------------
    # 6. ASSEMBLE OUTPUT
    # ------------------------------------------------------------------
    return {
        "startTime": start_ms,
        "endTime": end_ms,
        "pageNumber": 1,
        "pageLimit": 50,
        "order": "DESC",
        "resources": {
            "Video_Sources": video_sources,
        },
        "analytics": analytics,
        "propertyFilters": property_filters,
        "AttributeFilters": attribute_filters,
    }
