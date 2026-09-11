from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser

from .models import MatchedEvents

parser = PydanticOutputParser(pydantic_object=MatchedEvents)


def parse_llm_output(raw_output) -> tuple[MatchedEvents | None, str | None]:
    """
    Parse raw LLM output into MatchedEvents.
    Accepts both str and AIMessage — extracts .content if needed.

    Returns:
      (MatchedEvents, None)  — success
      (None, error_str)      — failure
    """

    if hasattr(raw_output, "content"):
        raw_output = raw_output.content

    try:
        parsed: MatchedEvents = parser.invoke(raw_output)
        return parsed, None
    except Exception as e:
        return None, f"Parse error: {e}"
