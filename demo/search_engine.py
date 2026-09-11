"""
Runs a parsed query (the pipeline's raw NLP output) against the dummy events.

Semantics mirror the downstream API payload built by transform.py:
  - time window        → startTime / endTime
  - resolved cameras   → resources.Video_Sources
  - extracted_fields   → analytics (event types, OR'ed) + propertyFilters
                         (rules within one event type are AND'ed)
  - attribute conditions → AttributeFilters (ALL = AND, ANY = OR)
"""

from __future__ import annotations

import re
from datetime import datetime

from demo.data_store import event_label

_NEGATIVE_OPS = {"notequal", "notcontains", "notin", "notlike"}


def _parse_dt(block: dict | None) -> datetime | None:
    if not block or not block.get("date"):
        return None
    combined = f"{block['date']} {block.get('time') or '00:00:00'}"
    for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    return None


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and "," in value:
        return [v.strip() for v in value.split(",") if v.strip()]
    return [value]


def _to_number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _equals(actual, expected) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        truthy = {"true", "1", "yes"}
        a = actual if isinstance(actual, bool) else str(actual).lower() in truthy
        e = expected if isinstance(expected, bool) else str(expected).lower() in truthy
        return a == e
    a_num, e_num = _to_number(actual), _to_number(expected)
    if a_num is not None and e_num is not None:
        return a_num == e_num
    return str(actual).strip().casefold() == str(expected).strip().casefold()


def _like(actual, pattern) -> bool:
    pattern = str(pattern)
    if "%" not in pattern and "*" not in pattern:
        return str(pattern).casefold() in str(actual).casefold()
    regex = re.escape(pattern).replace("%", ".*").replace(r"\*", ".*")
    return re.fullmatch(regex, str(actual), flags=re.IGNORECASE) is not None


def compare(actual, operator: str, expected) -> bool:
    """Evaluate one filter rule. Accepts both field-style ('GreaterThan') and
    attribute-style ('GREATERTHAN') operator names."""
    op = (operator or "equal").lower().replace("_", "")
    if actual is None:
        return op in _NEGATIVE_OPS or op == "wasupdated"

    if op == "equal":
        return _equals(actual, expected)
    if op == "notequal":
        return not _equals(actual, expected)
    if op in ("contains", "notcontains"):
        hit = str(expected).casefold() in str(actual).casefold()
        return hit if op == "contains" else not hit
    if op in ("in", "notin", "any"):
        hit = any(_equals(actual, v) for v in _as_list(expected))
        return not hit if op == "notin" else hit
    if op == "all":
        return all(str(v).casefold() in str(actual).casefold() for v in _as_list(expected))
    if op in ("like", "notlike"):
        hit = _like(actual, expected)
        return hit if op == "like" else not hit
    if op == "wasupdated":
        return True

    a = _to_number(actual)
    if op == "between":
        bounds = [_to_number(v) for v in _as_list(expected)]
        return a is not None and len(bounds) == 2 and None not in bounds and bounds[0] <= a <= bounds[1]
    e = _to_number(expected)
    if a is None or e is None:
        return False
    return {
        "greaterthan": a > e,
        "smallerthan": a < e,
        "greaterthanorequal": a >= e,
        "smallerthanorequal": a <= e,
    }.get(op, False)


def _describe_rule(field: str, operator: str, value) -> str:
    return f"{field} {operator} {value}"


def search_events(events: list[dict], nlp: dict) -> dict:
    """Filter *events* with the pipeline output *nlp*.

    Returns {"matches": [...], "filters": [(label, text), ...], "skipped": bool}.
    """
    if nlp.get("status") in ("irrelevant", "error"):
        return {"matches": [], "filters": [], "skipped": True}

    filters: list[tuple[str, str]] = []

    time_block = nlp.get("time") or {}
    start, end = _parse_dt(time_block.get("start")), _parse_dt(time_block.get("end"))
    if start or end:
        fmt = "%d %b %Y %H:%M"
        filters.append(("Time", f"{start.strftime(fmt) if start else '…'} → {end.strftime(fmt) if end else '…'}"))

    cameras = set((nlp.get("video_resources") or {}).get("resolved_cameras") or [])
    if cameras:
        names = sorted(cameras)
        shown = ", ".join(names[:3]) + (f" +{len(names) - 3} more" if len(names) > 3 else "")
        filters.append(("Cameras", f"{len(names)} · {shown}"))

    rules_by_event = {
        ef["event_name"]: [
            r for r in ef.get("relevant_fields", []) if r.get("field") and r.get("operator")
        ]
        for ef in (nlp.get("extracted_fields") or [])
    }
    for event_name, rules in rules_by_event.items():
        text = " · ".join(_describe_rule(r["field"], r["operator"], r["value"]) for r in rules)
        filters.append((event_label(event_name), text or "any"))

    attr_block = nlp.get("attribute_conditions") or {}
    conditions = [c for c in attr_block.get("conditions", []) if c.get("key")]
    condition_type = (attr_block.get("conditionType") or "ALL").upper()
    if conditions:
        text = " · ".join(_describe_rule(c["key"], c["operator"], c.get("value")) for c in conditions)
        filters.append((f"Attributes ({condition_type})", text))

    matches = []
    for event in events:
        ts = event["ts"]
        if start and ts < start:
            continue
        if end and ts > end:
            continue
        if cameras and event["camera_name"] not in cameras:
            continue
        if rules_by_event:
            rules = rules_by_event.get(event["event_type"])
            if rules is None:
                continue
            props = event["properties"]
            if not all(compare(props.get(r["field"]), r["operator"], r["value"]) for r in rules):
                continue
        if conditions:
            attrs = event.get("attributes", {})
            results = [compare(attrs.get(c["key"]), c["operator"], c.get("value")) for c in conditions]
            if not (any(results) if condition_type == "ANY" else all(results)):
                continue
        matches.append(event)

    return {"matches": matches, "filters": filters, "skipped": False}
