import json
import os
import re

import aiofiles

from .constants import OPERATORS


def normalize_event_to_filename(event_name: str) -> str:
    """
    Convert event name to schema filename.
    Removes trailing 'properties' or 'eventproperties' (space or underscore variants).

    Examples:
        "ANPR Properties"               → "anpr.json"
        "Objects_Entered_EventProperties" → "objects_entered.json"
    """
    name = event_name.lower().strip()
    name = name.replace("_", " ")
    name = re.sub(r"\b(eventproperties|properties)\b$", "", name).strip()
    name = re.sub(r"\s+", "_", name)
    return f"{name}.json"


async def load_schema(schema_dir: str, event_name: str) -> dict:
    """Load the JSON schema file for the given event name."""
    filename = normalize_event_to_filename(event_name)
    path = os.path.join(schema_dir, filename)

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Schema file not found for event '{event_name}' → {filename}"
        )

    async with aiofiles.open(path, "r") as f:
        content = await f.read()
    return json.loads(content)


def build_tool_schema(event_name: str, event_schema: dict) -> dict:
    """
    Dynamically build the structured output tool schema from the event's JSON schema.

    - Validates event_schema structure
    - field is constrained to a valid enum of field names from the event schema
    - Field type/enum info is injected into the tool description for LLM context
    - value accepts all types — fine-grained per-field enforcement is done by ResponseValidator
    - Uses a flat item schema (not oneOf+const per field) for reliable LLM output
    """
    # ── Validate ───────────────────────────────────────────────────────────────
    if not isinstance(event_schema, dict):
        raise ValueError(
            f"[{event_name}] event_schema must be a dict, got {type(event_schema)}"
        )

    properties = event_schema.get("properties")
    if not properties:
        raise ValueError(f"[{event_name}] event_schema missing or empty 'properties'")

    if not isinstance(properties, dict):
        raise ValueError(
            f"[{event_name}] event_schema['properties'] must be a dict, got {type(properties)}"
        )

    # ── Build field enum and description context ───────────────────────────────
    field_enum = list(properties.keys())

    # Inject per-field type + enum constraints into the description so the LLM
    # knows the expected value type for each field even though value is a union type
    field_descriptions = {
        name: {k: v for k, v in defn.items() if k in ("type", "enum", "description")}
        for name, defn in properties.items()
    }

    # ── Flat item schema ───────────────────────────────────────────────────────
    return {
        "name": "field_extraction_result",
        "description": (
            f"Extracted filter fields for the '{event_name}' event. "
            f"Field details: {json.dumps(field_descriptions)}"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "relevant_fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {
                                "type": "string",
                                "enum": field_enum,
                                "description": "Field name from the event schema",
                            },
                            "operator": {
                                "oneOf": [
                                    {"type": "string", "enum": OPERATORS},
                                    {"type": "null"},
                                ],
                                "description": "Comparison operator, or null if not determinable",
                            },
                            "value": {
                                "oneOf": [
                                    {"type": "string"},
                                    {"type": "number"},
                                    {"type": "boolean"},
                                    {
                                        "type": "array",
                                        "items": {
                                            "oneOf": [
                                                {"type": "string"},
                                                {"type": "number"},
                                            ]
                                        },
                                    },
                                    {"type": "null"},
                                ],
                                "description": "Value matching the field type from the schema, or null if not mentioned",
                            },
                            "query_snippet": {
                                "oneOf": [{"type": "string"}, {"type": "null"}],
                                "description": "Exact phrase from the query that led to this field and value",
                            },
                        },
                        "required": ["field", "operator", "value", "query_snippet"],
                    },
                }
            },
            "required": ["relevant_fields"],
        },
    }
