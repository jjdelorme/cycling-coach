"""Structured logging configuration for GCP Cloud Logging.

Sets up structlog with a JSON renderer that produces logs GCP understands natively:
- severity field maps to GCP log severity
- logging.googleapis.com/trace carries the request trace ID
- httpRequest field for request-level entries
- Short ERR-XXXXXXXX error IDs on 500s so clients can cite them in support

Usage:
    from server.logging_config import configure_logging, get_logger, bind_trace_id, get_trace_id

    configure_logging()                 # call once at startup — before any other imports
    logger = get_logger(__name__)       # module-level loggers
    bind_trace_id("abc-123")            # in middleware, per request
"""

import logging
import os
import sys
import secrets
import contextvars
from typing import Any

import structlog

# ---------------------------------------------------------------------------
# Request-scoped context (async-safe via contextvars)
# ---------------------------------------------------------------------------

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_span_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("span_id", default="")


def bind_trace_id(trace_id: str, span_id: str = "") -> None:
    """Set the trace/span ID for the current async context."""
    _trace_id_var.set(trace_id)
    _span_id_var.set(span_id)


def get_trace_id() -> str:
    return _trace_id_var.get()


def generate_trace_id() -> str:
    """Generate a new random trace ID (hex, 16 bytes = 32 chars)."""
    return secrets.token_hex(16)


def generate_error_id() -> str:
    """Generate a short human-readable error ID, e.g. ERR-A3F9B2C1.

    Uses 4 bytes (8 hex chars) for ~4 billion possible values, keeping
    collision probability negligible even at high error rates.
    """
    return "ERR-" + secrets.token_hex(4).upper()


# ---------------------------------------------------------------------------
# GCP severity mapping
# ---------------------------------------------------------------------------

_LEVEL_TO_GCP_SEVERITY = {
    "debug": "DEBUG",
    "info": "INFO",
    "warning": "WARNING",
    "error": "ERROR",
    "critical": "CRITICAL",
}


# ---------------------------------------------------------------------------
# structlog processors
# ---------------------------------------------------------------------------

def _add_gcp_fields(logger: Any, method: str, event_dict: dict) -> dict:
    """Rename structlog fields to GCP Cloud Logging field names."""
    # GCP severity (replaces 'level')
    level = event_dict.pop("level", method).lower()
    event_dict["severity"] = _LEVEL_TO_GCP_SEVERITY.get(level, "DEFAULT")

    # GCP trace field
    trace_id = _trace_id_var.get()
    if trace_id:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        if project:
            event_dict["logging.googleapis.com/trace"] = f"projects/{project}/traces/{trace_id}"
        else:
            event_dict["logging.googleapis.com/trace"] = trace_id

    span_id = _span_id_var.get()
    if span_id:
        event_dict["logging.googleapis.com/spanId"] = span_id

    # GCP uses 'message' not 'event'
    event_dict["message"] = event_dict.pop("event", "")

    return event_dict


def _drop_color_message(logger: Any, method: str, event_dict: dict) -> dict:
    """Remove uvicorn's color_message key which pollutes JSON output."""
    event_dict.pop("color_message", None)
    return event_dict


# ---------------------------------------------------------------------------
# stdlib logging → structlog bridge
# ---------------------------------------------------------------------------

class _StructlogHandler(logging.Handler):
    """Routes stdlib logging records into structlog so third-party libraries
    (uvicorn, httpx, google-auth) also emit structured JSON.

    Guard: if structlog's logger_factory is ever switched to stdlib's
    LoggerFactory, this handler would cause infinite recursion. The guard
    below prevents that by dropping records from the structlog logger itself.
    """

    # Track recursion per-thread to prevent infinite loops
    _emitting = threading_local = None

    def __init__(self):
        super().__init__()
        import threading
        self._local = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        # Prevent recursion if structlog itself emits via stdlib
        if getattr(self._local, "emitting", False):
            return
        self._local.emitting = True
        try:
            level_map = {
                logging.DEBUG: "debug",
                logging.INFO: "info",
                logging.WARNING: "warning",
                logging.ERROR: "error",
                logging.CRITICAL: "critical",
            }
            log_method = level_map.get(record.levelno, "info")
            sl_logger = structlog.get_logger(record.name)
            bound = getattr(sl_logger, log_method)

            kwargs: dict = {}
            if record.exc_info:
                kwargs["exc_info"] = record.exc_info

            bound(record.getMessage(), **kwargs)
        finally:
            self._local.emitting = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure_logging() -> None:
    """Configure structlog and stdlib logging. Call once at application startup.

    Must be called before any module-level logger = get_logger(__name__) calls
    in imported modules actually emit log entries (lazy binding is fine; emission
    before configure_logging completes will use structlog defaults).
    """
    # Dev mode only when ENVIRONMENT is explicitly set to a dev value.
    # Defaulting to "production" ensures Cloud Run (where ENVIRONMENT is unset)
    # always gets JSON output — never pretty-print.
    env = os.environ.get("ENVIRONMENT", "production").lower()
    is_dev = env in ("dev", "development", "local")

    shared_processors = [
        # Note: merge_contextvars merges structlog's own contextvars bindings
        # (set via structlog.contextvars.bind_contextvars). The trace_id/span_id
        # ContextVars used here are read directly in _add_gcp_fields, not via
        # structlog's context system. This processor is retained for any future
        # use of structlog.contextvars.bind_contextvars() elsewhere.
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _drop_color_message,
    ]

    if is_dev and sys.stderr.isatty():
        # Human-readable coloured output for local dev terminals
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # JSON output for Cloud Run / production.
        # ExceptionRenderer renders exception info as a structured dict so
        # Cloud Logging can index the exception type and message separately.
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.ExceptionRenderer(),
                _add_gcp_fields,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )

    # Route all stdlib logging through structlog so uvicorn, httpx, google-auth
    # etc. also emit structured JSON instead of plain text.
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(_StructlogHandler())
    root.setLevel(log_level)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("google.auth").setLevel(logging.WARNING)
    logging.getLogger("google.api_core").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a structlog logger bound to the given module name."""
    return structlog.get_logger(name)
