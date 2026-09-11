from __future__ import annotations

import json

from config import ATTRIBUTES_JSON_PATH

from .constants import AttributeValueType
from .models import Attribute


def load_attributes() -> list[Attribute]:
    """
    Load and parse attribute definitions from the configured path.
    """
    try:
        with open(ATTRIBUTES_JSON_PATH) as f:
            raw: list[dict] = json.load(f)
    except FileNotFoundError as e:
        raise ValueError(f"Attribute file not found: {ATTRIBUTES_JSON_PATH}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Attribute file contains invalid JSON: {e}") from e

    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON array, got {type(raw).__name__}")

    attributes = []
    for entry in raw:
        key = entry.get("key")
        value_type = entry.get("valueType")

        if not key:
            raise ValueError(f"Missing 'key' in entry: {entry}")
        if not value_type:
            raise ValueError(f"Missing 'valueType' in entry: {entry}")

        try:
            resolved_type = AttributeValueType[value_type]
        except KeyError as e:
            raise ValueError(
                f"Unknown valueType '{value_type}' for key '{key}'. "
                f"Valid types: {[t.name for t in AttributeValueType]}"
            ) from e

        attributes.append(Attribute(key=key, valueType=resolved_type))

    return attributes
