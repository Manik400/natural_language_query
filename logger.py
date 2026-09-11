import contextvars
import json
import logging
from datetime import datetime

# Context variables for request tracing
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="unknown"
)
node_name_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "node_name", default="unknown"
)


class StructuredLogFormatter(logging.Formatter):
    """Format logs as JSON for better parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "node_name": node_name_var.get(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Add extra fields if provided
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        return json.dumps(log_data)


def setup_logging(
    log_file: str = "pipeline.log",
    log_level: str = "INFO",
) -> logging.Logger:
    """
    Configure structured logging for the pipeline.

    Args:
        log_file: Path to log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("nli_pipeline")
    logger.setLevel(getattr(logging, log_level))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(StructuredLogFormatter())

    # File handler with rotation
    from logging.handlers import RotatingFileHandler

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(StructuredLogFormatter())

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(f"nli_pipeline.{name}")


def set_request_context(request_id: str, node_name: str = "unknown"):
    """Set context for current request."""
    request_id_var.set(request_id)
    node_name_var.set(node_name)


def get_request_context() -> dict:
    """Get current request context."""
    return {
        "request_id": request_id_var.get(),
        "node_name": node_name_var.get(),
    }
