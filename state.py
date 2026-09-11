from typing import Annotated, Any

from typing_extensions import TypedDict

# ─────────────────────────────────────────────
# Reducers
# ─────────────────────────────────────────────


def merge_source_attributions(a: dict, b: dict) -> dict:
    """Merge attribution dicts from parallel nodes without clobbering."""
    return {**a, **b}


# ─────────────────────────────────────────────
# Source Attribution Models
# ─────────────────────────────────────────────


class FieldEntry(TypedDict, total=False):
    field: str
    operator: str
    value: Any
    query_snippet: str


class FieldAttribution(TypedDict, total=False):
    query_part: str
    fields: list[FieldEntry]


class TimeAttribution(TypedDict, total=False):
    raw_time_query: str
    time_intent: str
    intent_subclass: str
    resolved_start: str
    resolved_end: str


class VideoAttribution(TypedDict, total=False):
    matched_token: str
    match_type: str
    confidence: float
    cameras: list[str]


class SourceAttributions(TypedDict, total=False):
    time: TimeAttribution
    video: list[VideoAttribution]
    fields: dict[str, FieldAttribution]


# ─────────────────────────────────────────────
# Attribute Extraction Models
# ─────────────────────────────────────────────


class AttributeCondition(TypedDict, total=False):
    key: str
    op: str
    value: Any


class AttributeConditions(TypedDict, total=False):
    conditionType: str
    conditions: list[AttributeCondition]


# ─────────────────────────────────────────────
# Pipeline State
# ─────────────────────────────────────────────


class PipelineState(TypedDict, total=False):
    # Input — written once at invocation, never by nodes
    query: str

    # Node outputs
    time: dict
    video_resources: dict
    extracted_fields: list[dict]
    attribute_conditions: AttributeConditions

    # Internal
    matched_events: list[dict]

    # Source attributions — merged across parallel nodes
    source_attributions: Annotated[SourceAttributions, merge_source_attributions]

    # Errors
    event_selection_error: dict | None
    attribute_extraction_error: dict | None
    time_extraction_error: dict | None
    video_resolution_error: dict | None
    field_extraction_error: dict | None
    field_extraction_errors: dict[str, dict]

    # Terminal
    status: str
    message: str
