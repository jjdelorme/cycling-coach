"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from server.routers import rides, pmc, analysis, planning, coaching, sync
from server.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Cycling Coach", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rides.router)
app.include_router(pmc.router)
app.include_router(analysis.router)
app.include_router(planning.router)
app.include_router(coaching.router)
app.include_router(sync.router)


@app.get("/api/health")
def health():
    from server.database import get_db
    with get_db() as conn:
        ride_count = conn.execute("SELECT COUNT(*) as cnt FROM rides").fetchone()["cnt"]
    return {"status": "ok", "rides": ride_count}


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
