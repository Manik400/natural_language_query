from typing import Optional


class NLIPipelineException(Exception):
    """Base exception for all NLI pipeline errors."""

    def __init__(
        self,
        message: str,
        error_code: str,
        node_name: Optional[str] = None,
        context: Optional[dict] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.node_name = node_name
        self.context = context or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert exception to dictionary for API response."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "node_name": self.node_name,
            "context": self.context,
        }


class QueryValidationException(NLIPipelineException):
    """Raised when query validation fails."""

    def __init__(self, message: str, context: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code="QUERY_VALIDATION_ERROR",
            node_name="query_validation",
            context=context,
        )


class EventSelectionException(NLIPipelineException):
    """Raised when event selection fails."""

    def __init__(self, message: str, context: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code="EVENT_SELECTION_ERROR",
            node_name="event_selection",
            context=context,
        )


class TimeExtractionException(NLIPipelineException):
    """Raised when time extraction fails."""

    def __init__(self, message: str, context: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code="TIME_EXTRACTION_ERROR",
            node_name="time_extraction",
            context=context,
        )


class VideoResolutionException(NLIPipelineException):
    """Raised when video resource resolution fails."""

    def __init__(self, message: str, context: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code="VIDEO_RESOLUTION_ERROR",
            node_name="video_resolution",
            context=context,
        )


class FieldExtractionException(NLIPipelineException):
    """Raised when field extraction fails."""

    def __init__(self, message: str, context: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code="FIELD_EXTRACTION_ERROR",
            node_name="field_extraction",
            context=context,
        )


class LLMException(NLIPipelineException):
    """Raised when LLM operations fail."""

    def __init__(
        self,
        message: str,
        llm_error: Optional[str] = None,
        context: Optional[dict] = None,
    ):
        full_context = context or {}
        if llm_error:
            full_context["llm_error"] = llm_error
        super().__init__(
            message=message,
            error_code="LLM_ERROR",
            node_name="llm_client",
            context=full_context,
        )


class AttributeValidationException(NLIPipelineException):
    """Raised when a single attribute condition fails validation
    (e.g. bad operator, type mismatch, duplicate key)."""

    def __init__(
        self,
        message: str,
        key: Optional[str] = None,
        context: Optional[dict] = None,
    ):
        full_context = context or {}
        if key:
            full_context["key"] = key
        super().__init__(
            message=message,
            error_code="ATTRIBUTE_VALIDATION_ERROR",
            node_name="attribute_validation",
            context=full_context,
        )


class TimeoutException(NLIPipelineException):
    """Raised when operation exceeds timeout."""

    def __init__(
        self,
        message: str,
        node_name: str,
        timeout_seconds: int,
        context: Optional[dict] = None,
    ):
        full_context = context or {}
        full_context["timeout_seconds"] = timeout_seconds
        super().__init__(
            message=message,
            error_code="TIMEOUT_ERROR",
            node_name=node_name,
            context=full_context,
        )
