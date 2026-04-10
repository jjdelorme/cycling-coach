"""FastAPI application entry point."""

import os
import time
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware

from server.logging_config import (
    configure_logging,
    get_logger,
    generate_trace_id,
    generate_error_id,
    bind_trace_id,
)
from opentelemetry import trace as otel_trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from server.telemetry import configure_telemetry, shutdown as telemetry_shutdown

# Configure structured logging before anything else imports logging
configure_logging()
logger = get_logger(__name__)

from server.routers import rides, pmc, analysis, planning, coaching, sync, athlete, admin, nutrition, withings as withings_router


def _read_version() -> str:
    version_file = os.path.join(os.path.dirname(__file__), "..", "VERSION")
    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            return f.read().strip()
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
            text=True, stderr=subprocess.DEVNULL
        ).strip().lstrip('v')
    except Exception:
        return "dev"


APP_VERSION = _read_version()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from server.config import GOOGLE_AUTH_ENABLED, JWT_SECRET
    if GOOGLE_AUTH_ENABLED and not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is required when GOOGLE_AUTH_ENABLED=true. "
                           "Set it via environment variable or Secret Manager.")
    logger.info("Starting cycling-coach", version=APP_VERSION)
    yield
    logger.info("Shutting down cycling-coach")
    telemetry_shutdown()


app = FastAPI(title="Cycling Coach", version=APP_VERSION, lifespan=lifespan)

# ---------------------------------------------------------------------------
# Middleware
#
# Starlette processes add_middleware() in REVERSE registration order:
# the LAST call added becomes the OUTERMOST layer (runs first on ingress).
# Registration order here:
#   1. CORSMiddleware              → added first  → innermost (runs last)
#   2. RequestLoggingMiddleware    → added second → middle layer
#   3. OTelTraceBridge             → added last   → outermost custom middleware
#
# FastAPIInstrumentor.instrument_app(app) injects its own middleware at the
# Starlette level *before* our add_middleware() calls take effect, so OTel's
# span is active by the time OTelTraceBridge.__call__() runs.
#
# Execution order on an incoming request:
#   OTelTraceBridge (reads OTel span, binds trace_id) → RequestLoggingMiddleware → route
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000",
        os.getenv("CORS_ALLOWED_ORIGIN", ""),
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class OTelTraceBridge:
    """Bridge OTel active span context into structlog's GCP log fields.

    Implemented as a raw ASGI middleware (not BaseHTTPMiddleware) so that
    bind_trace_id() runs in the same contextvars context as the route handler.
    BaseHTTPMiddleware.call_next() spawns a new anyio task group with a fresh
    context, causing the ContextVar set here to be invisible to the route.

    FastAPIInstrumentor creates the OTel span before this middleware runs
    (it is registered as the outermost middleware, so it executes after OTel
    has already set the active span in the current context). We read that span,
    convert trace_id/span_id to hex, and call bind_trace_id() so every
    structlog entry in this request carries logging.googleapis.com/trace and
    logging.googleapis.com/spanId that match the Cloud Trace entry.
    """

    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        span = otel_trace.get_current_span()
        span_context = span.get_span_context()
        if span_context.is_valid:
            trace_id_hex = format(span_context.trace_id, "032x")
            span_id_hex = format(span_context.span_id, "016x")
        else:
            # No active OTel span — fall back to a fresh random trace ID so
            # logs are still correlated within the request.
            trace_id_hex = generate_trace_id()
            span_id_hex = ""

        bind_trace_id(trace_id_hex, span_id_hex)

        async def send_with_trace_header(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("x-trace-id", trace_id_hex)
            await send(message)

        await self._app(scope, receive, send_with_trace_header)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log one structured entry per request with method, path, status, latency."""

    async def dispatch(self, request: Request, call_next):
        t0 = time.monotonic()
        path = request.url.path

        # Skip static asset noise
        if path.startswith("/assets/"):
            return await call_next(request)

        response = await call_next(request)
        elapsed_ms = (time.monotonic() - t0) * 1000
        status = response.status_code

        log = logger.info if status < 400 else (logger.warning if status < 500 else logger.error)
        # httpRequest is a GCP Cloud Logging structured payload — the log router
        # parses it into the log entry's httpRequest field for dashboards/alerts.
        # We log only the path (no query string) to avoid PII/token leakage.
        log(
            "http_request",
            method=request.method,
            path=path,
            status=status,
            latency_ms=round(elapsed_ms, 1),
            httpRequest={
                "requestMethod": request.method,
                "requestUrl": path,
                "status": status,
                "latency": f"{elapsed_ms / 1000:.3f}s",
                "remoteIp": request.client.host if request.client else "",
                "userAgent": request.headers.get("user-agent", ""),
            },
        )
        return response


app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(OTelTraceBridge)

# --- OpenTelemetry setup ---
# configure_telemetry() selects InMemorySpanExporter (TESTING=true) or
# CloudTraceSpanExporter (production). FastAPIInstrumentor injects its own
# middleware before our custom ones so the active span is ready when
# OTelTraceBridge.__call__() reads it.
configure_telemetry()
FastAPIInstrumentor.instrument_app(app)


# ---------------------------------------------------------------------------
# Global exception handler — catches unhandled 500s
#
# Note: FastAPI's ExceptionMiddleware intercepts HTTPException and
# RequestValidationError before this handler is reached — those return their
# own structured error responses without going through here. This handler
# fires only for truly unexpected exceptions that escape route handlers,
# which is exactly the set of errors that need an error_id.
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    error_id = generate_error_id()
    logger.error(
        "unhandled_exception",
        error_id=error_id,
        method=request.method,
        path=request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred.",
            "error_id": error_id,
        },
        headers={"X-Error-Id": error_id},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(rides.router)
app.include_router(pmc.router)
app.include_router(analysis.router)
app.include_router(planning.router)
app.include_router(coaching.router)
app.include_router(sync.router)
app.include_router(athlete.router)
app.include_router(admin.router)
app.include_router(nutrition.router)
app.include_router(withings_router.router)


@app.get("/api/health")
def health():
    from server.database import get_db
    with get_db() as conn:
        ride_count = conn.execute("SELECT COUNT(*) as cnt FROM rides").fetchone()["cnt"]
    return {"status": "ok", "rides": ride_count}


@app.get("/api/version")
def version():
    return {"version": APP_VERSION}


# ---------------------------------------------------------------------------
# Frontend SPA — serve React build if present
# ---------------------------------------------------------------------------

_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        file_path = os.path.join(_frontend_dist, path)
        if path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_frontend_dist, "index.html"))
