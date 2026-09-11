import config
from logger import get_logger
from nodes.attributes.run import extract_attributes
from nodes.events.run import select_events_with_error_handling
from nodes.fields.run import extract_fields_with_error_handling
from nodes.time.run import time_extraction_with_error_handling
from nodes.video_resource.run import VideoResolutionFallbackHandler
from state import PipelineState

logger = get_logger("pipeline_nodes")

# ─────────────────────────────────────────────
# Node: Event Selection
# ─────────────────────────────────────────────


async def node_event_selection(state: PipelineState) -> dict:
    logger.info("Entering event_selection node")

    try:
        result = await select_events_with_error_handling(
            query=state["query"],
            schema_dir=str(config.SCHEMA_DIR),
        )
    except Exception as e:
        logger.error(f"Event selection failed: {e}", exc_info=True)
        result = {
            "status": "error",
            "matched_events": [],
            "message": "Event selection service unavailable",
        }

    return {
        "matched_events": result.get("matched_events", []),
        "status": result.get("status", "success"),
        "message": result.get("message"),
        "event_selection_error": result.get("error"),
    }


# ─────────────────────────────────────────────
# Node: Attribute Extraction
# ─────────────────────────────────────────────


async def node_attribute_extraction(state: PipelineState) -> dict:
    logger.info("Entering attribute_extraction node")

    try:
        result = await extract_attributes(query=state["query"])

        condition_type = (
            result.conditionType.name if result.conditionType is not None else None
        )

        logger.info(
            "Attribute extraction complete",
            extra={
                "conditionType": condition_type,
                "condition_count": len(result.conditions),
            },
        )

        return {
            "attribute_conditions": {
                "conditionType": condition_type,
                "conditions": [c.model_dump() for c in result.conditions],
            },
            "attribute_extraction_error": None,
        }

    except Exception as e:
        logger.error(f"Attribute extraction failed: {e}", exc_info=True)
        return {
            "attribute_conditions": {
                "conditionType": None,
                "conditions": [],
            },
            "attribute_extraction_error": {
                "type": "attribute_extraction_error",
                "message": str(e),
            },
        }


# ─────────────────────────────────────────────
# Node: Time Extraction
# ─────────────────────────────────────────────


async def node_time_extraction(state: PipelineState) -> dict:
    logger.info("Entering time_extraction node")

    time_result = {
        "resolved": None,
        "llm_response": None,
        "validation": {"success": False},
        "error": None,
    }

    try:
        time_result = await time_extraction_with_error_handling(state["query"])
        logger.info("Time extraction completed")
    except Exception as e:
        logger.error(f"Time extraction node error: {e}")
        time_result = {
            "resolved": None,
            "error": {"type": "node_error", "message": str(e)},
        }

    resolved = time_result.get("resolved") or {}
    llm = time_result.get("llm_response") or {}

    time_out = {
        "start": resolved.get("start"),
        "end": resolved.get("end"),
    }

    time_attribution = {
        "raw_time_query": llm.get("raw_time_query"),
        "time_intent": llm.get("timeIntent"),
        "intent_subclass": llm.get("timeIntentSubClass"),
        "resolved_start": (
            f"{resolved.get('start', {}).get('date', '')} {resolved.get('start', {}).get('time', '')}".strip()
            if resolved
            else None
        ),
        "resolved_end": (
            f"{resolved.get('end', {}).get('date', '')} {resolved.get('end', {}).get('time', '')}".strip()
            if resolved
            else None
        ),
    }

    return {
        "time": time_out,
        "source_attributions": {"time": time_attribution},
        "time_extraction_error": time_result.get("error"),
    }


# ─────────────────────────────────────────────
# Node: Video Resolution
# ─────────────────────────────────────────────


def node_video_resolution(state: PipelineState) -> dict:
    logger.info("Entering video_resolution node")

    video_result = {
        "groups": [],
        "resolved_cameras": [],
        "error": None,
    }

    try:
        video_result = VideoResolutionFallbackHandler(
            config.VIDEO_JSON_PATH
        ).resolve_with_fallback(state["query"])
        logger.info("Video resolution completed")
    except Exception as e:
        logger.error(f"Video resolution node error: {e}")
        video_result = {
            "groups": [],
            "error": {"type": "node_error", "message": str(e)},
        }

    video_out = {
        "groups": video_result.get("groups", []),
        "resolved_cameras": video_result.get("resolved_cameras", []),
    }

    video_attributions = [
        {
            "matched_token": g.get("matched_token"),
            "match_type": g.get("match_type"),
            "confidence": g.get("confidence"),
            "cameras": g.get("cameras", []),
        }
        for g in video_result.get("groups", [])
    ]

    return {
        "video_resources": video_out,
        "source_attributions": {"video": video_attributions},
        "video_resolution_error": video_result.get("error"),
    }


# ─────────────────────────────────────────────
# Node: Field Extraction
# ─────────────────────────────────────────────


async def node_field_extraction(state: PipelineState) -> dict:
    logger.info("Entering field_extraction node")

    matched_events = state.get("matched_events", [])

    if not matched_events:
        logger.warning("No matched events for field extraction")
        return {
            "extracted_fields": [],
            "field_extraction_error": {
                "type": "no_matched_events",
                "recovered": True,
            },
        }

    try:
        raw_field_results = await extract_fields_with_error_handling(
            matched_events_response={
                "status": "success",
                "matched_events": matched_events,
            },
            schema_dir=str(config.SCHEMA_DIR),
        )

    except Exception as e:
        logger.error(f"Field extraction service error: {e}", exc_info=True)
        raw_field_results = [
            {
                "event_name": event["event_name"],
                "query_part": event.get("query_part", ""),
                "relevant_fields": [],
                "error": {"type": "service_error", "message": str(e)},
            }
            for event in matched_events
        ]

    extracted_fields = [
        {
            "event_name": r["event_name"],
            "relevant_fields": [
                {
                    "field": f.get("field"),
                    "operator": f.get("operator"),
                    "value": f.get("value"),
                }
                for f in r.get("relevant_fields", [])
            ],
        }
        for r in raw_field_results
    ]

    field_attributions = {}
    extraction_errors = {}

    for r in raw_field_results:
        event_name = r["event_name"]
        field_attributions[event_name] = {
            "query_part": r.get("query_part", ""),
            "fields": [
                {
                    "field": f.get("field"),
                    "operator": f.get("operator"),
                    "value": f.get("value"),
                    "query_snippet": f.get("query_snippet"),
                }
                for f in r.get("relevant_fields", [])
            ],
        }

        if r.get("error"):
            extraction_errors[event_name] = r.get("error")

    return {
        "extracted_fields": extracted_fields,
        "source_attributions": {"fields": field_attributions},
        "field_extraction_errors": extraction_errors,
    }


# ─────────────────────────────────────────────
# Node: Irrelevant Query
# ─────────────────────────────────────────────


def node_irrelevant(state: PipelineState) -> dict:
    logger.info("Entering irrelevant node")
    return {
        "status": "irrelevant",
        "message": "No relevant events found for the given query.",
    }
