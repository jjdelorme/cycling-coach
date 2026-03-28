"""Background sync service for bidirectional intervals.icu sync.

- Downloads rides from intervals.icu (source of truth for rides)
- Uploads planned workouts to intervals.icu (this app is source of truth for plans)
- Tracks sync status, watermarks, and progress
- Supports WebSocket live updates and REST polling
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from server.database import get_db
from server.services.intervals_icu import (
    fetch_activities,
    fetch_activity_streams,
    fetch_calendar_events,
    is_configured,
    map_activity_to_ride,
    push_workout,
)

logger = logging.getLogger(__name__)

# In-memory registry of active sync runs and their subscribers
_active_syncs: dict[str, dict] = {}
_subscribers: dict[str, list[asyncio.Queue]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _tlog(msg: str) -> str:
    """Prefix a log line with an ISO timestamp for sync run logs."""
    return f"[{_now_iso()}] {msg}"


# ---------------------------------------------------------------------------
# Watermark helpers
# ---------------------------------------------------------------------------

def get_watermark(key: str, conn=None) -> str | None:
    def _query(c):
        row = c.execute(
            "SELECT value FROM sync_watermarks WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return row["value"] if isinstance(row, dict) else row[0]
        return None
    if conn:
        return _query(conn)
    with get_db() as c:
        return _query(c)


def set_watermark(key: str, value: str, conn=None):
    def _update(c):
        c.execute(
            "INSERT INTO sync_watermarks (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, _now_iso()),
        )
    if conn:
        _update(conn)
    else:
        with get_db() as c:
            _update(c)


# ---------------------------------------------------------------------------
# Sync run persistence
# ---------------------------------------------------------------------------

def _create_sync_run(sync_id: str, conn=None):
    def _insert(c):
        c.execute(
            "INSERT INTO sync_runs (id, status, started_at) VALUES (?, ?, ?)",
            (sync_id, "running", _now_iso()),
        )
    if conn:
        _insert(conn)
    else:
        with get_db() as c:
            _insert(c)


def _update_sync_run(sync_id: str, conn=None, **kwargs):
    if not kwargs:
        return
    set_clauses = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [sync_id]
    def _update(c):
        c.execute(
            f"UPDATE sync_runs SET {set_clauses} WHERE id = ?",
            values,
        )
    if conn:
        _update(conn)
    else:
        with get_db() as c:
            _update(c)


def get_sync_run(sync_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sync_runs WHERE id = ?", (sync_id,)).fetchone()
    return dict(row) if row else None


def get_sync_history(limit: int = 20) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_last_sync() -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Subscriber / broadcast for WebSocket live updates
# ---------------------------------------------------------------------------

def subscribe(sync_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(sync_id, []).append(q)
    return q


def unsubscribe(sync_id: str, q: asyncio.Queue):
    subs = _subscribers.get(sync_id, [])
    if q in subs:
        subs.remove(q)
    if not subs:
        _subscribers.pop(sync_id, None)


async def _broadcast(sync_id: str, message: dict):
    """Send a message to all WebSocket subscribers for this sync run."""
    for q in _subscribers.get(sync_id, []):
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            pass
    # Also update in-memory state
    if sync_id in _active_syncs:
        _active_syncs[sync_id].update(message)


# ---------------------------------------------------------------------------
# Core sync logic
# ---------------------------------------------------------------------------

def _store_streams(ride_id: int, streams: dict, conn=None):
    """Store intervals.icu stream data as ride_records."""
    # streams is a dict like: [{"type":"time","data":[0,1,2,...]}, {"type":"watts","data":[...]}]
    # or a dict with keys: {"time": [...], "watts": [...], ...}
    stream_map = {}
    if isinstance(streams, list):
        for s in streams:
            stream_map[s.get("type", "")] = s.get("data", [])
    elif isinstance(streams, dict):
        stream_map = streams

    time_data = stream_map.get("time", [])
    if not time_data:
        return

    watts = stream_map.get("watts", [])
    hr = stream_map.get("heartrate", [])
    cadence = stream_map.get("cadence", [])
    velocity = stream_map.get("velocity_smooth", [])
    altitude = stream_map.get("altitude", [])
    distance = stream_map.get("distance", [])
    latlng_raw = stream_map.get("latlng", [])

    # Parse latlng — intervals.icu may return [lat, lng] pairs or flat values
    latlng_pairs = []
    if latlng_raw:
        if latlng_raw and isinstance(latlng_raw[0], (list, tuple)):
            latlng_pairs = latlng_raw  # already [lat, lng] pairs
        # else: flat values or None — skip lat/lon

    n = len(time_data)
    rows = []
    for i in range(n):
        lat, lon = None, None
        if latlng_pairs and i < len(latlng_pairs) and latlng_pairs[i]:
            lat, lon = latlng_pairs[i][0], latlng_pairs[i][1]
        rows.append((
            ride_id,
            None,  # timestamp_utc
            watts[i] if i < len(watts) else None,
            hr[i] if i < len(hr) else None,
            cadence[i] if i < len(cadence) else None,
            velocity[i] if i < len(velocity) else None,
            altitude[i] if i < len(altitude) else None,
            distance[i] if i < len(distance) else None,
            lat,
            lon,
            None,  # temperature
        ))

    def _insert(c):
        c.executemany(
            "INSERT INTO ride_records (ride_id, timestamp_utc, power, heart_rate, cadence, speed, altitude, distance, lat, lon, temperature) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    if conn:
        _insert(conn)
    else:
        with get_db() as c:
            _insert(c)
    logger.info("Stored %d stream records for ride %d", len(rows), ride_id)


def _backfill_start_location(ride_id: int, streams, conn=None):
    """Update start_lat/start_lon on ride from stream GPS data."""
    stream_map = {}
    if isinstance(streams, list):
        for s in streams:
            stream_map[s.get("type", "")] = s.get("data", [])
    elif isinstance(streams, dict):
        stream_map = streams

    latlng_raw = stream_map.get("latlng", [])
    if not latlng_raw:
        return

    # Find first valid GPS point
    for point in latlng_raw:
        if point and isinstance(point, (list, tuple)) and len(point) >= 2:
            lat, lon = point[0], point[1]
            if lat and lon:
                def _update(c):
                    c.execute(
                        "UPDATE rides SET start_lat = ?, start_lon = ? WHERE id = ? AND start_lat IS NULL",
                        (lat, lon, ride_id),
                    )
                if conn:
                    _update(conn)
                else:
                    with get_db() as c:
                        _update(c)
                break


async def _download_rides(sync_id: str, log_lines: list[str], conn) -> tuple[int, int, str | None]:
    """Download rides from intervals.icu that we don't already have.

    Returns (downloaded, skipped, earliest_new_ride_date).
    """
    t0 = time.monotonic()
    downloaded = 0
    skipped = 0
    earliest_date: str | None = None

    # Determine date range from watermark
    watermark = get_watermark("rides_newest", conn=conn)
    if watermark:
        # Re-fetch from watermark date (not day after) — a ride may have been
        # uploaded to intervals.icu after the sync that set the watermark.
        # Dedup logic handles any rides we already have.
        oldest = datetime.fromisoformat(watermark).strftime("%Y-%m-%d")
    else:
        oldest = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    newest = datetime.now().strftime("%Y-%m-%d")

    if oldest > newest:
        msg = "Rides already up to date"
        logger.info(msg)
        log_lines.append(_tlog(msg))
        await _broadcast(sync_id, {"phase": "rides", "detail": msg})
        return 0, 0, None

    msg = f"Fetching rides from {oldest} to {newest}"
    logger.info(msg)
    log_lines.append(_tlog(msg))
    await _broadcast(sync_id, {"phase": "rides", "detail": msg})

    activities = await asyncio.to_thread(fetch_activities, oldest, newest)

    if not activities:
        msg = "No activities found from intervals.icu"
        logger.info(msg)
        log_lines.append(_tlog(msg))
        await _broadcast(sync_id, {"phase": "rides", "detail": msg})
        return 0, 0, None

    msg = f"Found {len(activities)} activities from intervals.icu"
    logger.info(msg)
    log_lines.append(_tlog(msg))
    await _broadcast(sync_id, {"phase": "rides", "detail": msg, "total": len(activities)})

    # Get existing rides for dedup: by filename AND by (date, distance) fingerprint.
    # Distance is more reliable than duration because moving-time vs elapsed-time
    # differs between sources (Garmin auto-pause, Strava, intervals.icu).
    existing_filenames = set()
    existing_fingerprints = set()
    rows = conn.execute("SELECT filename, date, distance_m FROM rides").fetchall()
    for r in rows:
        row = dict(r)
        existing_filenames.add(row["filename"])
        # Fingerprint: (date, distance rounded to nearest 100m)
        dist = round((row["distance_m"] or 0) / 100) * 100
        existing_fingerprints.add((row["date"], dist))

    # Early exit: check if all activities already exist locally
    has_new = False
    for activity in activities:
        ride = map_activity_to_ride(activity)
        if ride is None:
            continue
        if ride["filename"] in existing_filenames:
            continue
        dist = round((ride["distance_m"] or 0) / 100) * 100
        if (ride["date"], dist) in existing_fingerprints:
            continue
        has_new = True
        break
    if not has_new:
        msg = f"All {len(activities)} activities already synced"
        logger.info(msg)
        log_lines.append(_tlog(msg))
        await _broadcast(sync_id, {"phase": "rides", "detail": msg})
        set_watermark("rides_newest", newest, conn=conn)
        logger.info("Ride download completed in %.1fs: %d downloaded, %d skipped",
                    time.monotonic() - t0, 0, len(activities))
        return 0, len(activities), None

    for i, activity in enumerate(activities):
        ride = map_activity_to_ride(activity)
        if ride is None:
            skipped += 1
            continue

        # Check filename match (exact dedup for re-syncs)
        if ride["filename"] in existing_filenames:
            skipped += 1
            continue

        # Check fingerprint match (cross-source dedup: JSON import vs intervals.icu)
        # Same date + same distance (within 100m) = same ride
        dist = round((ride["distance_m"] or 0) / 100) * 100
        fingerprint = (ride["date"], dist)
        if fingerprint in existing_fingerprints:
            skipped += 1
            continue

        # Insert ride
        columns = [k for k in ride if ride[k] is not None]
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        values = [ride[k] for k in columns]

        try:
            conn.execute(
                f"INSERT INTO rides ({col_names}) VALUES ({placeholders})",
                values,
            )
            # Get the inserted ride's ID for stream data
            ride_row = conn.execute(
                "SELECT id FROM rides WHERE filename = ?", (ride["filename"],)
            ).fetchone()
            ride_db_id = ride_row["id"] if ride_row else None

            downloaded += 1
            existing_filenames.add(ride["filename"])
            existing_fingerprints.add(fingerprint)
            if earliest_date is None or ride["date"] < earliest_date:
                earliest_date = ride["date"]
            detail = f"Downloaded ride: {ride['date']} ({ride.get('sport', 'ride')})"
            logger.info(detail)
            log_lines.append(_tlog(detail))

            # Fetch and store per-second stream data
            if ride_db_id:
                icu_id = activity.get("id", "")
                try:
                    t_stream = time.monotonic()
                    streams = await asyncio.to_thread(fetch_activity_streams, icu_id)
                    if streams:
                        _store_streams(ride_db_id, streams, conn=conn)
                        # Backfill start_lat/start_lon from stream GPS data
                        _backfill_start_location(ride_db_id, streams, conn=conn)
                        log_lines.append(_tlog(f"  + stored stream data for {ride['date']} ({(time.monotonic()-t_stream)*1000:.0f}ms)"))
                except Exception as se:
                    logger.warning("Could not fetch streams for %s: %s", icu_id, se)

        except Exception as e:
            err = f"Error inserting ride {ride['filename']}: {e}"
            logger.error(err)
            log_lines.append(_tlog(err))

        if (i + 1) % 5 == 0 or i == len(activities) - 1:
            await _broadcast(sync_id, {
                "phase": "rides",
                "detail": f"Processed {i + 1}/{len(activities)} activities",
                "rides_downloaded": downloaded,
                "rides_skipped": skipped,
            })

    # Update watermark to newest date we processed
    if activities:
        set_watermark("rides_newest", newest, conn=conn)

    logger.info("Ride download completed in %.1fs: %d downloaded, %d skipped",
                time.monotonic() - t0, downloaded, skipped)
    return downloaded, skipped, earliest_date


async def _upload_workouts(sync_id: str, log_lines: list[str], conn) -> tuple[int, int]:
    """Upload planned workouts to intervals.icu that haven't been synced yet."""
    t0 = time.monotonic()
    uploaded = 0
    skipped = 0

    # Get watermark - tracks the newest date we've synced workouts for
    watermark = get_watermark("workouts_synced_through", conn=conn)
    today = datetime.now().strftime("%Y-%m-%d")

    # Only sync workouts from today onward (no point syncing past workouts)
    start_date = today
    # Look ahead 4 weeks
    end_date = (datetime.now() + timedelta(days=28)).strftime("%Y-%m-%d")

    msg = f"Checking workouts to sync: {start_date} to {end_date}"
    logger.info(msg)
    log_lines.append(_tlog(msg))
    await _broadcast(sync_id, {"phase": "workouts", "detail": msg})

    # Get our planned workouts with XML
    local_workouts = conn.execute(
        "SELECT id, date, name, workout_xml, total_duration_s FROM planned_workouts "
        "WHERE date >= ? AND date <= ? AND workout_xml IS NOT NULL ORDER BY date",
        (start_date, end_date),
    ).fetchall()

    if not local_workouts:
        msg = "No upcoming workouts to sync"
        logger.info(msg)
        log_lines.append(_tlog(msg))
        await _broadcast(sync_id, {"phase": "workouts", "detail": msg})
        return 0, 0

    msg = f"Found {len(local_workouts)} upcoming planned workouts"
    logger.info(msg)
    log_lines.append(_tlog(msg))

    # Fetch existing events from intervals.icu to avoid duplicates
    try:
        remote_events = await asyncio.to_thread(
            fetch_calendar_events, start_date, end_date
        )
    except Exception as e:
        logger.warning("Could not fetch remote events for dedup: %s", e)
        remote_events = []

    # Build set of (date, name) for dedup
    remote_keys = set()
    for ev in remote_events:
        ev_date = (ev.get("start_date_local") or "")[:10]
        ev_name = ev.get("name", "")
        remote_keys.add((ev_date, ev_name))

    for i, w in enumerate(local_workouts):
        w = dict(w)
        w_date = w["date"]
        w_name = w["name"] or "Workout"

        if (w_date, w_name) in remote_keys:
            skipped += 1
            detail = f"Skipped (already on intervals.icu): {w_date} {w_name}"
            logger.info(detail)
            log_lines.append(_tlog(detail))
            continue

        try:
            result = await asyncio.to_thread(
                push_workout,
                date=w_date,
                name=w_name,
                zwo_xml=w["workout_xml"],
                moving_time_secs=int(w.get("total_duration_s") or 0),
            )
            if result.get("status") == "success":
                uploaded += 1
                detail = f"Uploaded workout: {w_date} {w_name}"
                logger.info(detail)
                log_lines.append(_tlog(detail))
            else:
                err = f"Failed to upload {w_date} {w_name}: {result.get('message', result.get('error', 'unknown'))}"
                logger.error(err)
                log_lines.append(_tlog(err))
        except Exception as e:
            err = f"Error uploading workout {w_date} {w_name}: {e}"
            logger.error(err)
            log_lines.append(_tlog(err))

        if (i + 1) % 3 == 0 or i == len(local_workouts) - 1:
            await _broadcast(sync_id, {
                "phase": "workouts",
                "detail": f"Processed {i + 1}/{len(local_workouts)} workouts",
                "workouts_uploaded": uploaded,
                "workouts_skipped": skipped,
            })

    if uploaded > 0:
        set_watermark("workouts_synced_through", end_date, conn=conn)

    logger.info("Workout upload completed in %.1fs: %d uploaded, %d skipped",
                time.monotonic() - t0, uploaded, skipped)
    return uploaded, skipped


async def run_sync(sync_id: str | None = None) -> str:
    """Execute a full bidirectional sync. Returns the sync_id."""
    if sync_id is None:
        sync_id = str(uuid.uuid4())[:8]

    if not is_configured():
        raise RuntimeError("intervals.icu not configured. Set API key and Athlete ID in Settings.")

    # Check for already-running sync
    for sid, info in _active_syncs.items():
        if info.get("status") == "running":
            raise RuntimeError(f"Sync already in progress: {sid}")

    _active_syncs[sync_id] = {"status": "running", "started_at": _now_iso()}
    t_sync = time.monotonic()

    log_lines: list[str] = []
    errors: list[str] = []

    try:
        with get_db() as conn:
            _create_sync_run(sync_id, conn=conn)
            conn.commit()

            await _broadcast(sync_id, {"status": "running", "phase": "rides", "detail": "Starting ride download..."})

            # Phase 1: Download rides
            rides_dl, rides_skip, earliest = await _download_rides(sync_id, log_lines, conn)
            conn.commit()

            await _broadcast(sync_id, {"status": "running", "phase": "workouts", "detail": "Starting workout upload..."})

            # Phase 2: Upload workouts
            wo_up, wo_skip = await _upload_workouts(sync_id, log_lines, conn)
            conn.commit()

            # Phase 3: Recompute PMC if we downloaded new rides
            if rides_dl > 0:
                msg = "Recomputing daily metrics (PMC)..."
                log_lines.append(_tlog(msg))
                await _broadcast(sync_id, {"phase": "pmc", "detail": msg})
                try:
                    from server.ingest import compute_daily_pmc
                    compute_daily_pmc(conn, since_date=earliest)
                    conn.commit()
                    log_lines.append(_tlog("PMC recomputed successfully"))
                except Exception as e:
                    err = f"PMC recomputation failed: {e}"
                    logger.error(err)
                    log_lines.append(_tlog(err))
                    errors.append(err)

            status = "completed"
            total_elapsed = time.monotonic() - t_sync
            summary = (
                f"Sync complete in {total_elapsed:.1f}s: {rides_dl} rides downloaded, {rides_skip} skipped, "
                f"{wo_up} workouts uploaded, {wo_skip} skipped"
            )
            logger.info(summary)
            log_lines.append(_tlog(summary))

            # Persist final state
            _update_sync_run(
                sync_id,
                conn=conn,
                status=status,
                completed_at=_now_iso(),
                rides_downloaded=rides_dl,
                rides_skipped=rides_skip,
                workouts_uploaded=wo_up,
                workouts_skipped=wo_skip,
                errors="\n".join(errors) if errors else None,
                log="\n".join(log_lines),
            )

    except Exception as e:
        status = "failed"
        err = f"Sync failed: {e}"
        logger.error(err, exc_info=True)
        log_lines.append(_tlog(err))
        errors.append(str(e))
        rides_dl = rides_skip = wo_up = wo_skip = 0

        # Persist failure state with a fresh connection
        _update_sync_run(
            sync_id,
            status=status,
            completed_at=_now_iso(),
            rides_downloaded=rides_dl,
            rides_skipped=rides_skip,
            workouts_uploaded=wo_up,
            workouts_skipped=wo_skip,
            errors="\n".join(errors) if errors else None,
            log="\n".join(log_lines),
        )

    final_msg = {
        "status": status,
        "sync_id": sync_id,
        "rides_downloaded": rides_dl,
        "rides_skipped": rides_skip,
        "workouts_uploaded": wo_up,
        "workouts_skipped": wo_skip,
        "errors": errors or None,
    }
    await _broadcast(sync_id, final_msg)

    _active_syncs[sync_id] = final_msg
    _active_syncs[sync_id]["completed_at"] = _now_iso()

    return sync_id


def start_sync_background() -> str:
    """Start a sync in the background. Returns sync_id immediately."""
    sync_id = str(uuid.uuid4())[:8]
    _active_syncs[sync_id] = {"status": "pending", "started_at": _now_iso()}

    loop = asyncio.get_event_loop()
    loop.create_task(run_sync(sync_id))

    return sync_id


def get_sync_status(sync_id: str) -> dict | None:
    """Get current sync status - checks in-memory first, then DB."""
    if sync_id in _active_syncs:
        return {**_active_syncs[sync_id], "sync_id": sync_id}
    return get_sync_run(sync_id)


def get_sync_overview() -> dict:
    """Get overall sync status including watermarks and last run."""
    last_run = get_last_sync()
    rides_watermark = get_watermark("rides_newest")
    workouts_watermark = get_watermark("workouts_synced_through")

    running = None
    for sid, info in _active_syncs.items():
        if info.get("status") == "running":
            running = sid
            break

    return {
        "configured": is_configured(),
        "running_sync_id": running,
        "last_sync": last_run,
        "watermarks": {
            "rides_newest": rides_watermark,
            "workouts_synced_through": workouts_watermark,
        },
    }
