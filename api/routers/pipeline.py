from uuid import uuid4

from fastapi import APIRouter, HTTPException

from api.schemas import QueryRequest
from exceptions import NLIPipelineException
from graph import run_pipeline as execute_pipeline
from logger import get_logger, set_request_context

router = APIRouter(tags=["Pipeline"])
logger = get_logger("pipeline")


@router.post("/pipeline")
async def pipeline_endpoint(request: QueryRequest):
    """
    Run the full NLI pipeline with comprehensive error handling.

    Set transform=true in the request body to receive an API-ready payload
    instead of the raw NLP output.
    """
    request_id = str(uuid4())
    set_request_context(request_id, "pipeline")

    logger.info(
        "Pipeline request received",
        extra={
            "query_length": len(request.query),
            "transform_output": request.transform,
        },
    )

    try:
        logger.info("Executing pipeline...")
        result = await execute_pipeline(
            query=request.query,
            transform_output=request.transform,
        )

        if result.get("status") == "irrelevant":
            return {
                "status": "irrelevant",
                "message": result.get(
                    "message", "No relevant events found for the given query."
                ),
                "request_id": request_id,
            }

        logger.info(
            "Pipeline execution successful",
            extra={"status": result.get("status")},
        )

        result["request_id"] = request_id
        return result

    except NLIPipelineException as e:
        logger.error(
            f"Pipeline exception: {e.error_code}",
            extra={"error": e.to_dict()},
        )
        return {
            "status": "error",
            "message": e.message,
            "error": e.to_dict(),
            "request_id": request_id,
            "query": request.query,
        }

    except TimeoutError:
        logger.error("Pipeline execution timed out")
        raise HTTPException(status_code=504, detail="Pipeline execution timed out")

    except Exception as e:
        logger.error(
            f"Unexpected pipeline error: {type(e).__name__}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")
