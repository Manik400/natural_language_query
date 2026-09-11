from __future__ import annotations

from typing import Any

from .constants import MULTI_VALUE_OPERATORS, AttributeValueType, Operators


def parse_value(
    raw: str | None,
    value_type: AttributeValueType,
    operator: Operators | None = None,
) -> Any:
    # Guard: WASUPDATED and similar operators legitimately have null values
    if raw is None:
        if operator in MULTI_VALUE_OPERATORS:
            raise ValueError("Multi-value operator requires a value, got null.")
        return None

    raw = raw.strip()

    if not raw:
        raise ValueError("Value must not be empty.")

    if operator in MULTI_VALUE_OPERATORS:
        items = [v.strip() for v in raw.split(",") if v.strip()]
        if not items:
            raise ValueError("Expected at least one value.")
        if operator == Operators.BETWEEN and len(items) != 2:
            raise ValueError(f"BETWEEN requires exactly 2 values, got {len(items)}.")
        return [parse_value(item, value_type) for item in items]

    match value_type:
        case AttributeValueType.string:
            if not raw:
                raise ValueError("String value must not be empty.")
            return raw

        case AttributeValueType.number:
            try:
                return int(raw) if "." not in raw else float(raw)
            except ValueError:
                raise ValueError(f"Expected a number, got: '{raw}'")

        case AttributeValueType.boolean:
            lower = raw.lower()
            if lower in {"true", "1", "yes"}:
                return True
            if lower in {"false", "0", "no"}:
                return False
            raise ValueError(
                f"Expected a boolean (true/false/yes/no/1/0), got: '{raw}'"
            )
