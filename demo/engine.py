"""
Parses a query with either the real LLM pipeline (AI mode) or the rule-based
offline parser (rules mode). Both return the same raw NLP JSON shape as
graph.run_pipeline(), so the UI and the search engine don't care which ran.
"""

from __future__ import annotations

import asyncio

from config import get_settings
from demo.rules_events import extract_attribute_conditions, select_events
from demo.rules_fields import extract_fields
from demo.rules_time import extract_time
from pipeline_nodes import node_video_resolution

MODE_AI = "ai"
MODE_RULES = "rules"


def missing_llm_settings() -> list[str]:
    """Names of required LLM settings that are not set (empty list = AI mode available)."""
    settings = get_settings()
    required = {"OPENAI_API_KEY": settings.OPENAI_API_KEY, "LLM_MODEL": settings.LLM_MODEL}
    return [name for name, value in required.items() if not value.strip()]


def ai_available() -> bool:
    return not missing_llm_settings()


def _time_state(time_result: dict) -> dict:
    """Shape a time result exactly like pipeline_nodes.node_time_extraction does."""
    resolved = time_result.get("resolved") or {}
    llm = time_result.get("llm_response") or {}

    def joined(part):
        block = resolved.get(part) or {}
        return f"{block.get('date', '')} {block.get('time', '')}".strip() if resolved else None

    return {
        "time": {"start": resolved.get("start"), "end": resolved.get("end")},
        "source_attributions": {"time": {
            "raw_time_query": llm.get("raw_time_query"),
            "time_intent": llm.get("timeIntent"),
            "intent_subclass": llm.get("timeIntentSubClass"),
            "resolved_start": joined("start"),
            "resolved_end": joined("end"),
        }},
        "time_extraction_error": time_result.get("error"),
    }


def _fields_state(raw_results: list[dict]) -> dict:
    """Shape field results exactly like pipeline_nodes.node_field_extraction does."""
    keep = ("field", "operator", "value")
    return {
        "extracted_fields": [
            {"event_name": r["event_name"],
             "relevant_fields": [{k: f.get(k) for k in keep} for f in r.get("relevant_fields", [])]}
            for r in raw_results
        ],
        "source_attributions": {"fields": {
            r["event_name"]: {
                "query_part": r.get("query_part", ""),
                "fields": [{**{k: f.get(k) for k in keep}, "query_snippet": f.get("query_snippet")}
                           for f in r.get("relevant_fields", [])],
            }
            for r in raw_results
        }},
        "field_extraction_errors": {r["event_name"]: r["error"] for r in raw_results if r.get("error")},
    }


async def run_rules_pipeline(query: str) -> dict:
    events = select_events(query)
    attributes = extract_attribute_conditions(query)
    result = {
        "query": query,
        "status": events["status"],
        "message": None,
        "attribute_conditions": attributes,
        "event_selection_error": None,
        "attribute_extraction_error": None,
    }

    has_attributes = any(c.get("value") not in (None, "", []) for c in attributes["conditions"])
    if not events["matched_events"] and not has_attributes:
        return {**result, "status": "irrelevant",
                "message": "No relevant events found for the given query."}

    time_part = _time_state(extract_time(query))
    video_part = node_video_resolution({"query": query})
    fields_part = _fields_state(await extract_fields(query, events["matched_events"]))

    return {
        **result,
        **time_part,
        **video_part,
        **fields_part,
        "source_attributions": {
            **time_part["source_attributions"],
            **video_part["source_attributions"],
            **fields_part["source_attributions"],
        },
    }


async def run_ai_pipeline(query: str) -> dict:
    from graph import run_pipeline  # imported lazily: pulls in LangGraph + LangChain

    return await run_pipeline(query)


def parse_query(query: str, mode: str = MODE_RULES) -> dict:
    """Synchronous entry point for the UI."""
    use_ai = mode == MODE_AI and ai_available()
    result = asyncio.run(run_ai_pipeline(query) if use_ai else run_rules_pipeline(query))
    result["engine"] = MODE_AI if use_ai else MODE_RULES
    return result
