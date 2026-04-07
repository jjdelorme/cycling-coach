"""FastAPI application entry point."""

import os
import time
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from server.logging_config import (
    configure_logging,
    get_logger,
    generate_trace_id,
    generate_error_id,
    bind_trace_id,
)

# Configure structured logging before anything else imports logging
configure_logging()
logger = get_logger(__name__)

from server.routers import rides, pmc, analysis, planning, coaching, sync, athlete, admin
from server.database import init_db


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
    init_db()
    yield
    logger.info("Shutting down cycling-coach")


app = FastAPI(title="Cycling Coach", version=APP_VERSION, lifespan=lifespan)

# ---------------------------------------------------------------------------
# Middleware
#
# Starlette processes add_middleware() in REVERSE registration order:
# the LAST call added becomes the OUTERMOST layer (runs first on ingress).
# Registration order here:
#   1. CORSMiddleware       → added first  → innermost (runs last)
#   2. RequestLoggingMiddleware → added second → middle layer
#   3. TraceMiddleware      → added last   → outermost (runs first on ingress)
#
# Execution order on an incoming request:
#   TraceMiddleware (sets trace_id) → RequestLoggingMiddleware (logs with trace_id) → route
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


class TraceMiddleware(BaseHTTPMiddleware):
    """Assign a trace ID to every request and expose it on the response."""

    async def dispatch(self, request: Request, call_next):
        # Honour incoming W3C traceparent if present, otherwise generate fresh
        traceparent = request.headers.get("traceparent", "")
        if traceparent:
            # traceparent format: 00-<trace-id>-<parent-id>-<flags>
            parts = traceparent.split("-")
            trace_id = parts[1] if len(parts) >= 2 else generate_trace_id()
            span_id = parts[2] if len(parts) >= 3 else ""
        else:
            trace_id = generate_trace_id()
            span_id = ""

        bind_trace_id(trace_id, span_id)

        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


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
app.add_middleware(TraceMiddleware)


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
