"""FastAPI application entry point."""

import logging
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware

from server.routers import rides, pmc, analysis, planning, coaching, sync, athlete, admin
from server.database import init_db

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _read_version() -> str:
    version_file = os.path.join(os.path.dirname(__file__), "..", "VERSION")
    try:
        with open(version_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "dev"

APP_VERSION = _read_version()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from server.config import GOOGLE_AUTH_ENABLED, JWT_SECRET
    if GOOGLE_AUTH_ENABLED and not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is required when GOOGLE_AUTH_ENABLED=true. "
                           "Set it via environment variable or Secret Manager.")
    init_db()
    yield


app = FastAPI(title="Cycling Coach", version=APP_VERSION, lifespan=lifespan)

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

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        t0 = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - t0) * 1000
        path = request.url.path
        if not path.startswith("/assets/"):
            logger.info("%s %s %d %.0fms", request.method, path, response.status_code, elapsed_ms)
        return response

app.add_middleware(RequestLoggingMiddleware)

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


# Serve frontend static files (React build)
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(_frontend_dist):
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")

    # SPA fallback: serve index.html for all non-API routes
    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        # Try to serve the exact file first
        file_path = os.path.join(_frontend_dist, path)
        if path and os.path.isfile(file_path):
            return FileResponse(file_path)
        # Fall back to index.html for SPA routing
        return FileResponse(os.path.join(_frontend_dist, "index.html"))
