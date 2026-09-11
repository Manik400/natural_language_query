import asyncio
import json
import os
from collections import Counter
from typing import Any

import aiofiles
from jsonschema import Draft202012Validator, RefResolver

from .schema_loader import build_tool_schema

# ── ResponseValidator ──────────────────────────────────────────────────────────


class ResponseValidator:

    OPERATOR_RULES = {
        "Equal": {
            "allowed_types": ["string", "number", "integer", "boolean"],
            "value_type": "scalar",
        },
        "NotEqual": {
            "allowed_types": ["string", "number", "integer", "boolean"],
            "value_type": "scalar",
        },
        "GreaterThan": {"allowed_types": ["number", "integer"], "value_type": "scalar"},
        "SmallerThan": {"allowed_types": ["number", "integer"], "value_type": "scalar"},
        "GreaterThanOrEqual": {
            "allowed_types": ["number", "integer"],
            "value_type": "scalar",
        },
        "SmallerThanOrEqual": {
            "allowed_types": ["number", "integer"],
            "value_type": "scalar",
        },
        "Contains": {"allowed_types": ["string"], "value_type": "string"},
        "NotContains": {"allowed_types": ["string"], "value_type": "string"},
        "In": {"allowed_types": ["string", "number", "integer"], "value_type": "list"},
        "NotIn": {
            "allowed_types": ["string", "number", "integer"],
            "value_type": "list",
        },
        "Between": {
            "allowed_types": ["number", "integer", "string"],
            "value_type": "range",
        },
        "Like": {"allowed_types": ["string"], "value_type": "string"},
        "NotLike": {"allowed_types": ["string"], "value_type": "string"},
    }

    def __init__(self, schema_dir: str):
        self.SCHEMA_DIR = schema_dir

    async def _load_schema_registry(self) -> dict[str, dict]:
        paths = [
            os.path.join(root, file)
            for root, _, files in os.walk(self.SCHEMA_DIR)
            for file in files
            if file.endswith(".json")
        ]

        async def _read(path: str) -> tuple[str, dict]:
            async with aiofiles.open(path) as f:
                content = await f.read()
            schema = json.loads(content)
            schema_id = schema.get("$id")
            if not schema_id:
                raise ValueError(f"[SCHEMA ERROR] Missing $id in {path}")
            return schema_id, schema

        pairs = await asyncio.gather(*[_read(p) for p in paths])
        return dict(pairs)

    def _get_field_type(self, schema: dict, field_name: str) -> str | None:
        return schema.get("properties", {}).get(field_name, {}).get("type")

    def _validate_operator(
        self, field_name: str, operator: str, value: Any, schema: dict
    ):
        if operator not in self.OPERATOR_RULES:
            return False, f"Invalid operator '{operator}'"

        field_type = self._get_field_type(schema, field_name)
        rule = self.OPERATOR_RULES[operator]

        if field_type not in rule["allowed_types"]:
            return (
                False,
                f"Operator '{operator}' not allowed for field type '{field_type}'",
            )

        vt = rule["value_type"]

        if vt == "scalar" and isinstance(value, (list, dict)):
            return False, f"Operator '{operator}' expects a scalar value"

        if vt == "string" and not isinstance(value, str):
            return False, f"Operator '{operator}' expects a string value"

        if vt == "list" and (not isinstance(value, list) or not value):
            return False, f"Operator '{operator}' expects a non-empty list"

        if vt == "range":
            if not isinstance(value, list) or len(value) != 2:
                return False, f"Operator '{operator}' expects [min, max]"
            if value[0] > value[1]:
                return False, f"Operator '{operator}' range start must be <= end"

        return True, None

    async def schema_validation(self, data: dict, schema: dict) -> dict:
        registry = await self._load_schema_registry()
        resolver = RefResolver.from_schema(schema, store=registry)
        validator = Draft202012Validator(schema, resolver=resolver)

        properties = schema.get("properties", {})

        if (
            not isinstance(data.get("relevant_fields"), list)
            or not data["relevant_fields"]
        ):
            return {
                "event": data.get("event"),
                "relevant_fields": [],
                "valid": False,
                "error": "relevant_fields missing or empty",
            }

        fields = [f.get("field") for f in data["relevant_fields"]]
        field_counts = Counter(fields)
        validated_fields = []

        for entry in data["relevant_fields"]:
            field = entry.get("field")
            operator = entry.get("operator")
            value = entry.get("value")

            if field not in properties:
                validated_fields.append(
                    {**entry, "valid": False, "error": f"Invalid field '{field}'"}
                )
                continue

            if field_counts[field] > 1:
                validated_fields.append(
                    {**entry, "valid": False, "error": f"Duplicate field '{field}'"}
                )
                continue

            ok, error = self._validate_operator(field, operator, value, schema)
            if not ok:
                validated_fields.append({**entry, "valid": False, "error": error})
                continue

            errors = list(validator.iter_errors({field: value}))
            if errors:
                validated_fields.append(
                    {**entry, "valid": False, "error": errors[0].message}
                )
            else:
                validated_fields.append({**entry, "valid": True})

        return {"event": data.get("event"), "relevant_fields": validated_fields}


# ── Two-stage validation pipeline ─────────────────────────────────────────────


def _validate_against_tool_schema(
    event_name: str, fields: list[dict], event_schema: dict
) -> list[dict]:
    """
    Stage 1: Pre-validate raw LLM output against the tool schema.

    Catches:
      - field names not in the field enum
      - operator values not in the operator enum
      - value types outside the allowed union
      - missing required keys (field, operator, value, query_snippet)

    Returns only fields that pass tool schema validation.
    """
    tool_schema = build_tool_schema(event_name, event_schema)
    item_schema = tool_schema["parameters"]["properties"]["relevant_fields"]["items"]

    valid_fields = []
    for entry in fields:
        errors = list(Draft202012Validator(item_schema).iter_errors(entry))
        if not errors:
            valid_fields.append(entry)
        else:
            error_messages = "; ".join(e.message for e in errors)
            print(
                f"[{event_name}] Tool schema pre-validation failed for "
                f"field '{entry.get('field')}': {error_messages}"
            )

    return valid_fields


async def validate_fields(
    event_name: str,
    fields: list[dict],
    event_schema: dict,
    validator: ResponseValidator,
) -> list[dict]:
    """
    Two-stage validation pipeline for extracted fields.

    Stage 1 — Tool schema (build_tool_schema):
        Validates field names enum, operator enum, value union type, required keys.
        Fields failing this stage are dropped with a log message.

    Stage 2 — ResponseValidator.schema_validation:
        Validates operator compatibility with field type, value type/enum constraints,
        and duplicate field names from the event schema.
        Returns only fields where valid=True.
    """
    tool_valid_fields = _validate_against_tool_schema(event_name, fields, event_schema)

    if not tool_valid_fields:
        return []

    validated = await validator.schema_validation(
        {"event": event_name, "relevant_fields": tool_valid_fields}, event_schema
    )

    return [f for f in validated.get("relevant_fields", []) if f.get("valid") is True]
