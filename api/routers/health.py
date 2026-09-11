import datetime

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
    }


@router.get("/status")
def get_status():
    """Service status endpoint."""
    return {
        "pipeline": "ready",
        "llm_model": "available",
        "timestamp": datetime.datetime.now().isoformat(),
    }
