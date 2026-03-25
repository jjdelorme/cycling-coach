"""Sync endpoints: REST API for triggering/polling and WebSocket for live updates."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from typing import Optional

from server.services.sync import (
    get_sync_history,
    get_sync_overview,
    get_sync_status,
    run_sync,
    start_sync_background,
    subscribe,
    unsubscribe,
)
from server.services.intervals_icu import is_configured

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/start")
async def start_sync():
    """Start a background sync. Returns immediately with a sync_id for polling.

    The sync_id can be used with:
    - GET /api/sync/status/{sync_id} to poll status
    - WebSocket /api/sync/ws/{sync_id} for live updates
    """
    if not is_configured():
        raise HTTPException(
            status_code=400,
            detail="intervals.icu not configured. Set API key and Athlete ID in Settings.",
        )

    try:
        sync_id = start_sync_background()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        "sync_id": sync_id,
        "status": "pending",
        "poll_url": f"/api/sync/status/{sync_id}",
        "ws_url": f"/api/sync/ws/{sync_id}",
    }


@router.get("/status/{sync_id}")
async def sync_status(sync_id: str):
    """Poll the status of a sync run."""
    status = get_sync_status(sync_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return status


@router.get("/overview")
async def sync_overview():
    """Get overall sync status: last run, watermarks, whether a sync is running."""
    return get_sync_overview()


@router.get("/history")
async def sync_history_endpoint(limit: Optional[int] = Query(20, ge=1, le=100)):
    """Get recent sync run history."""
    return get_sync_history(limit)


@router.websocket("/ws/{sync_id}")
async def sync_websocket(websocket: WebSocket, sync_id: str):
    """WebSocket endpoint for live sync updates.

    Connect to receive real-time progress messages for a sync run.
    Messages are JSON objects with fields like:
        {"status": "running", "phase": "rides", "detail": "...", "rides_downloaded": 5}
    Final message will have status "completed" or "failed".
    """
    await websocket.accept()
    logger.info("WebSocket connected for sync %s", sync_id)

    q = subscribe(sync_id)

    try:
        # Send current status immediately
        current = get_sync_status(sync_id)
        if current:
            await websocket.send_json(current)

            # If already completed, close
            if current.get("status") in ("completed", "failed"):
                await websocket.close()
                return

        # Stream updates
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
                await websocket.send_json(msg)

                # Close after final status
                if msg.get("status") in ("completed", "failed"):
                    break
            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for sync %s", sync_id)
    except Exception as e:
        logger.error("WebSocket error for sync %s: %s", sync_id, e)
    finally:
        unsubscribe(sync_id, q)
