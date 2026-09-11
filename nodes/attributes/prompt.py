from __future__ import annotations

from .constants import ConditionType, Operators
from .models import Attribute


def build_extraction_prompt(query: str, attributes: list[Attribute]) -> str:
    attr_descriptions = "\n".join(
        f'  - key: "{a.key}", valueType: "{a.valueType.name}"' for a in attributes
    )

    operator_descriptions = "\n".join(f"  - {op.name} ({op.value})" for op in Operators)

    condition_type_descriptions = "\n".join(
        f"  - {ct.name} ({ct.value})" for ct in ConditionType
    )

    return f"""
You are a query parser. Extract filter conditions from the query string below.

## Declared Attributes
{attr_descriptions}

## Available Operators
{operator_descriptions}

## Condition Types
{condition_type_descriptions}
  ANY: match if at least one condition is true (OR logic)
  ALL: match if all conditions are true (AND logic)

## Query
{query}

## Instructions

- Parse each filter condition from the query.
- Match keys only against declared attributes above.
- If no conditions match any declared attribute key, you MUST return conditionType as null and conditions as an empty list. Do not assign ANY or ALL.
- Only if at least one valid condition is found, determine conditionType (ANY or ALL) based on explicit keywords (e.g. "or" → ANY, "and" → ALL). Default to ALL if ambiguous.
- Identify the correct operator from the available operators list.
- Extract the value(s) as-is (raw string). For multi-value operators (IN, NOTIN, BETWEEN, ANY, ALL), return values as a comma-separated string.
- For WASUPDATED, value should be null.
- Skip keys not in declared attributes or with empty values.
- Return ONLY valid JSON, no explanation, no markdown, no code fences.

## Output Format
{{
  "conditionType": "<ANY|ALL|null>",
  "conditions": [
    {{
      "key": "<attribute key>",
      "operator": "<OPERATOR_NAME>",
      "raw_value": "<extracted raw value or null>",
      "raw_slice": "<the original fragment from query for this condition>"
    }}
  ]
}}
""".strip()
