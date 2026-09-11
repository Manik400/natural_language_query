from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser

from .models import ParsedIntent

parser = PydanticOutputParser(pydantic_object=ParsedIntent)


def parse_llm_output(raw_output: str) -> tuple[ParsedIntent | None, str | None]:
    """
    Parse raw LLM output into a ParsedIntent.

    PydanticOutputParser handles:
      - markdown fence stripping  (``` and ```json)
      - json.loads
      - field validation via Pydantic:
          raw_time_query     → required key, value can be null
          timeIntent         → required key, non-null string
          timeIntentSubClass → required key, non-null string
          params             → required key, value can be null

    Returns:
      (ParsedIntent, None)   — success
      (None, error_str)      — failure
    """
    try:
        parsed: ParsedIntent = parser.invoke(raw_output)
    except Exception as e:
        return None, f"Parse error: {e}"

    return parsed, None
