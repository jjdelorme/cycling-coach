"""Sync endpoints: REST API for triggering/polling and WebSocket for live updates."""

import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, Query
from typing import Optional

from server.auth import CurrentUser, require_read, require_write

from server.services.sync import (
    _store_streams,
    backfill_laps_from_icu,
    get_sync_history,
    get_sync_overview,
    get_sync_status,
    run_sync,
    start_sync_background,
    sync_single_ride_background,
    subscribe,
    unsubscribe,
)
from server.database import get_db
from server.logging_config import get_logger
from server.services.intervals_icu import fetch_activity_streams, is_configured

logger = get_logger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/start")
async def start_sync(user: CurrentUser = Depends(require_write)):
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
async def sync_status(sync_id: str, user: CurrentUser = Depends(require_read)):
    """Poll the status of a sync run."""
    status = get_sync_status(sync_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return status


@router.get("/overview")
async def sync_overview(user: CurrentUser = Depends(require_read)):
    """Get overall sync status: last run, watermarks, whether a sync is running."""
    return get_sync_overview()


@router.get("/history")
async def sync_history_endpoint(limit: Optional[int] = Query(20, ge=1, le=100), user: CurrentUser = Depends(require_read)):
    """Get recent sync run history."""
    return get_sync_history(limit)


@router.post("/ride/{icu_id}")
async def sync_single_ride(icu_id: str, user: CurrentUser = Depends(require_write)):
    """Start a background sync for a single ride."""
    if not is_configured():
        raise HTTPException(status_code=400, detail="intervals.icu not configured")
    
    sync_id = sync_single_ride_background(icu_id)
    return {"status": "started", "sync_id": sync_id}

@router.post("/backfill-streams")
async def backfill_streams(limit: Optional[int] = Query(50, ge=1, le=200), user: CurrentUser = Depends(require_write)):
    """Backfill per-second stream data for rides synced from intervals.icu that are missing records."""
    if not is_configured():
        raise HTTPException(status_code=400, detail="intervals.icu not configured")

    with get_db() as conn:
        # Find rides from intervals.icu (filename starts with icu_) that have no records
        rows = conn.execute(
            "SELECT r.id, r.filename, r.start_time FROM rides r "
            "WHERE r.filename LIKE ? "
            "AND NOT EXISTS (SELECT 1 FROM ride_records rr WHERE rr.ride_id = r.id) "
            "ORDER BY r.start_time DESC LIMIT ?",
            ("icu_%", limit),
        ).fetchall()

    if not rows:
        return {"message": "All rides already have stream data", "backfilled": 0}

    backfilled = 0
    errors = []
    for row in rows:
        row = dict(row)
        icu_id = row["filename"].replace("icu_", "")
        try:
            streams = await asyncio.to_thread(fetch_activity_streams, icu_id)
            if streams:
                _store_streams(row["id"], streams)
                backfilled += 1
                logger.info("streams_backfilled", ride_id=row["id"], start_time=row["start_time"])
        except Exception as e:
            errors.append(f"{row['start_time']}: {e}")
            logger.warning("streams_backfill_failed", ride_id=row["id"], start_time=row["start_time"], error=str(e))

    return {
        "backfilled": backfilled,
        "total_missing": len(rows),
        "errors": errors[:10] if errors else None,
    }


@router.post("/backfill-laps")
async def backfill_laps(user: CurrentUser = Depends(require_write)):
    """Backfill lap/interval data from intervals.icu for rides missing laps."""
    if not is_configured():
        raise HTTPException(status_code=400, detail="intervals.icu not configured")

    result = await asyncio.to_thread(backfill_laps_from_icu)
    return result


@router.websocket("/ws/{sync_id}")
async def sync_websocket(websocket: WebSocket, sync_id: str):
    """WebSocket endpoint for live sync updates.

    Connect to receive real-time progress messages for a sync run.
    Messages are JSON objects with fields like:
        {"status": "running", "phase": "rides", "detail": "...", "rides_downloaded": 5}
    Final message will have status "completed" or "failed".
    """
    await websocket.accept()
    logger.info("ws_connected", sync_id=sync_id)

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
        logger.info("ws_disconnected", sync_id=sync_id)
    except Exception as e:
        logger.error("ws_error", sync_id=sync_id, error=str(e), exc_info=e)
    finally:
        unsubscribe(sync_id, q)
