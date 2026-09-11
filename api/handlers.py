from fastapi import FastAPI, HTTPException


def register_exception_handlers(app: FastAPI):
    """Register all exception handlers on the app."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        """Handle HTTP exceptions with structured response."""
        return {
            "status": "error",
            "message": exc.detail,
            "status_code": exc.status_code,
        }
