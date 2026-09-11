from __future__ import annotations

from collections import Counter
from typing import Any

from .constants import OPERATOR_RULES, AttributeValueType, Operators
from .models import Attribute, AttributeExtractionResult
from .parser import parse_value


def validate_operator(
    key: str,
    operator: Operators,
    value: Any,
    value_type: AttributeValueType,
) -> tuple[bool, str | None]:
    rule = OPERATOR_RULES.get(operator)
    if not rule:
        return False, f"Unknown operator '{operator.name}'"

    if value_type not in rule["allowed_types"]:
        return (
            False,
            f"Operator '{operator.name}' not allowed for type '{value_type.name}'",
        )

    vt = rule["value_type"]

    match vt:
        case "none":
            pass

        case "scalar":
            if isinstance(value, list):
                return False, f"Operator '{operator.name}' expects a scalar, got list"

        case "list":
            if not isinstance(value, list) or not value:
                return False, f"Operator '{operator.name}' expects a non-empty list"

        case "range":
            if not isinstance(value, list) or len(value) != 2:
                return False, f"Operator '{operator.name}' expects [min, max]"
            if value[0] > value[1]:
                return False, f"Operator '{operator.name}' range start must be <= end"

    return True, None


def pre_validate(
    items: list[dict],
    attribute_map: dict[str, Attribute],
) -> list[dict]:
    """
    Stage 1 — Pre-validate raw LLM output.

    Catches:
      - keys not in declared attributes
      - unknown operator names
      - missing required fields (key, operator, raw_slice)

    Returns only items that pass pre-validation.
    """
    valid_items = []

    for item in items:
        key = item.get("key", "").strip()
        op_name = item.get("operator", "").strip().upper()
        raw_slice = item.get("raw_slice", "").strip()

        if not key:
            print(f"[PRE-VALIDATION] Skipping item with missing key: {item}")
            continue

        if key not in attribute_map:
            print(f"[PRE-VALIDATION] Unknown key '{key}' — not in declared attributes")
            continue

        if not op_name or op_name not in Operators.__members__:
            print(f"[PRE-VALIDATION] Unknown operator '{op_name}' for key '{key}'")
            continue

        if not raw_slice:
            print(f"[PRE-VALIDATION] Missing raw_slice for key '{key}'")
            continue

        valid_items.append(item)

    return valid_items


def build_conditions(
    items: list[dict],
    attribute_map: dict[str, Attribute],
) -> list[AttributeExtractionResult]:
    """
    Stage 2 — Operator compatibility, value type, and duplicate key validation.

    Validates:
      - duplicate keys
      - operator compatibility with attribute valueType
      - value type correctness (scalar / list / range / none)

    Returns only conditions that pass all checks.
    """
    key_counts = Counter(item.get("key") for item in items)
    conditions: list[AttributeExtractionResult] = []

    for item in items:
        key = item.get("key", "").strip()
        op_name = item.get("operator", "").strip().upper()
        raw_value = item.get("raw_value")
        raw_slice = item.get("raw_slice", "").strip()

        if key_counts[key] > 1:
            print(f"[VALIDATION] Duplicate key '{key}' — skipping")
            continue

        operator = Operators[op_name]
        attr = attribute_map[key]

        if operator == Operators.WASUPDATED or raw_value is None:
            conditions.append(
                AttributeExtractionResult(
                    key=key,
                    valueType=attr.valueType,
                    operator=operator,
                    value=None,
                    raw_slice=raw_slice,
                )
            )
            continue

        if not str(raw_value).strip():
            print(f"[VALIDATION] Empty value for key '{key}' — skipping")
            continue

        try:
            parsed_value = parse_value(str(raw_value), attr.valueType, operator)
        except ValueError as e:
            print(f"[VALIDATION] Invalid value for key '{key}': {e} — skipping")
            continue

        ok, error = validate_operator(key, operator, parsed_value, attr.valueType)
        if not ok:
            print(f"[VALIDATION] '{key}': {error} — skipping")
            continue

        conditions.append(
            AttributeExtractionResult(
                key=key,
                valueType=attr.valueType,
                operator=operator,
                value=parsed_value,
                raw_slice=raw_slice,
            )
        )

    return conditions
