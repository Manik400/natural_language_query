from __future__ import annotations

from .prompt import EVENT_SELECTION_PROMPT


def build_events_block(schemas: list[dict]) -> str:
    """
    Format schemas into a readable block for prompt injection.
    """
    lines = []
    for schema in schemas:
        title = schema["title"]
        description = schema.get("description", "No description provided.")

        lines.append(f"TITLE: {title}")
        lines.append(f"DESCRIPTION: {description}")
        lines.append("-" * 50)

    return "\n".join(lines)


def build_prompt(
    query: str,
    schemas: list[dict],
) -> tuple[str, list[str]]:
    """
    Build the final prompt and return it along with the valid events whitelist.

    Args:
        query:   User's natural language query
        schemas: List of loaded event schemas

    Returns:
        prompt:       Final formatted prompt string
        valid_events: List of valid event title strings for post-validation
    """
    valid_events = [s["title"] for s in schemas]
    events_block = build_events_block(schemas)

    prompt = EVENT_SELECTION_PROMPT.format(query=query, events=events_block)

    return prompt, valid_events
