import json

from langchain_core.messages import HumanMessage, SystemMessage

from llm.client import get_llm

# ─────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a technical documentation assistant for a video surveillance analytics platform.
Given an event name and a list of property names, return ONLY valid JSON — no markdown, no explanation.

The JSON must follow this exact structure:
{
  "event_description": "<one concise sentence describing what this analytics event detects>",
  "property_descriptions": {
    "<property_name>": "<one concise sentence describing the property's meaning in context>",
    ...
  }
}

Rules:
- Descriptions must be specific, technical, and grounded in surveillance/analytics context.
- Do NOT include generic filler like "This property represents...".
- Property descriptions must reflect the property's role within the specific event type.
- Return only the JSON object. No preamble, no trailing text.\
"""


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────


def generate_event_and_property_docs(event_name: str, properties: list[str]) -> dict:
    """
    Call the LLM to generate:
      - a one-sentence description for the event
      - a one-sentence description for each property

    Returns a dict:
      {
        "event_description": str,
        "property_descriptions": { property_name: str, ... }
      }

    Falls back to placeholder strings on any LLM or parse failure so that
    the schema sync never crashes mid-thread.
    """
    llm = get_llm()

    user_message = f"Event name: {event_name}\n" f"Properties: {json.dumps(properties)}"

    try:
        response = llm.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_message),
            ]
        )

        raw = response.content.strip()

        # Strip accidental markdown fences (```json ... ```)
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        docs = json.loads(raw)

        if "event_description" not in docs or "property_descriptions" not in docs:
            raise ValueError("LLM response missing required keys.")

        return docs

    except Exception as exc:
        return {
            "event_description": (
                f"Analytics event detecting {event_name} occurrences in video surveillance."
                f" (LLM error: {exc})"
            ),
            "property_descriptions": {
                p: f"{p} attribute of the {event_name} analytic event."
                for p in properties
            },
        }
