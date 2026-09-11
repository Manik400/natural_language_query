from fastapi import APIRouter

import config
from api.schemas import QueryRequest
from logger import get_logger
from nodes.attributes.run import extract_attributes
from nodes.events.run import select_events_with_error_handling
from nodes.fields.run import extract_fields_with_error_handling
from nodes.time.run import time_extraction_with_error_handling
from nodes.video_resource.run import VideoResolutionFallbackHandler

router = APIRouter(prefix="/debug", tags=["Debug"])
logger = get_logger("debug")


@router.post("/datetime")
async def extract_time(request: QueryRequest):
    """Debug endpoint for time extraction."""
    try:
        return await time_extraction_with_error_handling(request.query)
    except Exception as e:
        logger.error(f"Time extraction error: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/video_resources")
def resolve_video(request: QueryRequest):
    """Debug endpoint for video resolution."""
    try:
        handler = VideoResolutionFallbackHandler(config.VIDEO_JSON_PATH)
        return handler.resolve_with_fallback(request.query)
    except Exception as e:
        logger.error(f"Video resolution error: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/events")
async def resolve_events(request: QueryRequest):
    """Debug endpoint for event selection."""
    try:
        return await select_events_with_error_handling(
            query=request.query,
            schema_dir=str(config.SCHEMA_DIR),
        )
    except Exception as e:
        logger.error(f"Event selection error: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/fields")
async def resolve_fields(request: QueryRequest):
    """Debug endpoint for field extraction using real event extraction."""
    try:
        # Step 1: Extract events
        events_response = await select_events_with_error_handling(
            query=request.query,
            schema_dir=str(config.SCHEMA_DIR),
        )

        # If event extraction failed, return early
        if events_response.get("status") != "success":
            return events_response

        # Step 2: Use extracted events for field extraction
        return await extract_fields_with_error_handling(
            matched_events_response=events_response,
            schema_dir=str(config.SCHEMA_DIR),
        )

    except Exception as e:
        logger.error(f"Field extraction error: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/attributes")
async def resolve_attributes(request: QueryRequest):
    """Debug endpoint for attribute extraction."""
    try:
        result = await extract_attributes(request.query)
        return {"status": "success", "result": result.model_dump()}
    except Exception as e:
        logger.error(f"Attribute extraction error: {e}")
        return {"status": "error", "error": str(e)}
