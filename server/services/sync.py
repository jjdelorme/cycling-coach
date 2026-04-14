"""Background sync service for bidirectional intervals.icu sync.

- Downloads rides from intervals.icu (source of truth for rides)
- Uploads planned workouts to intervals.icu (this app is source of truth for plans)
- Tracks sync status, watermarks, and progress
- Supports WebSocket live updates and REST polling
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from server.database import get_db
from server.logging_config import get_logger
from server.metrics import calculate_np, process_ride_samples
from server.queries import get_latest_metric
from server.services.intervals_icu import (
    compute_sync_hash,
    fetch_activities,
    fetch_activity_fit_laps,
    fetch_activity_streams,
    fetch_calendar_events,
    find_matching_workout,
    is_configured,
    map_activity_to_ride,
    push_workout,
)

logger = get_logger(__name__)

# In-memory registry of active sync runs and their subscribers
_active_syncs: dict[str, dict] = {}
_subscribers: dict[str, list[asyncio.Queue]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _tlog(msg: str) -> str:
    """Prefix a log line with an ISO timestamp for sync run logs."""
    return f"[{_now_iso()}] {msg}"


def _get_athlete_tz():
    """Return UTC for background sync date windows.

    Background sync runs without an HTTP request context, so there is no
    X-Client-Timezone header. Using UTC means the fetch window could be off
    by up to one calendar day at timezone boundaries. This is acceptable
    because:
      - Ride dedup (filename + date+distance fingerprint) prevents duplicates
      - The watermark prevents re-downloading already-synced rides
      - Planned workout dedup uses (date, name) pairs
    """
    from zoneinfo import ZoneInfo
    return ZoneInfo("UTC")


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


def _enrich_laps_with_np(laps: list[dict], stream_map: dict[str, list]) -> None:
    """Calculate NP for each lap using stream power data.

    Slices the watts stream by lap boundaries (using cumulative timer times)
    and computes NP for any lap missing it.
    """
    import numpy as np

    watts = stream_map.get("watts", [])
    time_data = stream_map.get("time", [])
    if not watts or not time_data or len(watts) != len(time_data):
        return

    power_arr = np.array(watts, dtype=float)
    time_arr = np.array(time_data, dtype=float)

    # Build lap boundaries from cumulative timer times
    offset = 0.0
    for lap in laps:
        duration = lap.get("total_timer_time")
        if not duration or duration <= 0:
            offset += duration or 0
            continue

        # Already has NP from source data — skip
        if lap.get("normalized_power"):
            offset += duration
            continue

        lap_start = offset
        lap_end = offset + duration

        # Select samples within this lap's time window
        mask = (time_arr >= lap_start) & (time_arr < lap_end)
        lap_power = power_arr[mask]

        if len(lap_power) > 0:
            np_val = calculate_np(lap_power)
            if np_val and np_val > 0:
                lap["normalized_power"] = int(round(np_val))

        offset = lap_end


def _extract_streams(streams: dict | list) -> dict[str, list]:
    """Normalize intervals.icu stream data into a dict of lists.
    Handles both list-of-dicts and dict-of-lists formats.
    Ensures a 'time' stream exists by generating one if missing.
    """
    stream_map = {}
    if isinstance(streams, list):
        for s in streams:
            if isinstance(s, dict) and "type" in s:
                stream_map[s["type"]] = s.get("data") or []
    elif isinstance(streams, dict):
        for k, v in streams.items():
            stream_map[k] = v or []

    # Ensure 'time' exists if possible
    if "time" not in stream_map or not stream_map["time"]:
        # Find the longest other stream to determine duration
        max_len = 0
        for k, v in stream_map.items():
            if isinstance(v, list) and k != "latlng":
                max_len = max(max_len, len(v))
        if max_len > 0:
            stream_map["time"] = list(range(max_len))
            
    return stream_map


def _store_streams(ride_id: int, streams: dict | list, conn=None):
    """Store intervals.icu stream data as ride_records."""
    stream_map = _extract_streams(streams)
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
    logger.info("streams_stored", ride_id=ride_id, record_count=len(rows))


def _backfill_start_location(ride_id: int, streams, conn=None):
    """Update start_lat/start_lon on ride from stream GPS data."""
    stream_map = _extract_streams(streams)
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


def _store_laps(ride_id: int, laps: list[dict], conn=None):
    """Store lap/interval data for a ride."""
    rows = [
        (ride_id, l["lap_index"], l["start_time"], l["total_timer_time"],
         l["total_elapsed_time"], l["total_distance"], l["avg_power"], l["normalized_power"], l["max_power"],
         l["avg_hr"], l["max_hr"], l["avg_cadence"], l["max_cadence"], l["avg_speed"], l["max_speed"],
         l["total_ascent"], l["total_descent"], l["total_calories"], l["total_work"],
         l["intensity"], l["lap_trigger"], l["wkt_step_index"],
         l["start_lat"], l["start_lon"], l["end_lat"], l["end_lon"], l["avg_temperature"])
        for l in laps
    ]

    def _insert(c):
        c.executemany(
            """INSERT INTO ride_laps (ride_id, lap_index, start_time, total_timer_time,
               total_elapsed_time, total_distance, avg_power, normalized_power, max_power,
               avg_hr, max_hr, avg_cadence, max_cadence, avg_speed, max_speed,
               total_ascent, total_descent, total_calories, total_work,
               intensity, lap_trigger, wkt_step_index,
               start_lat, start_lon, end_lat, end_lon, avg_temperature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    if conn:
        _insert(conn)
    else:
        with get_db() as c:
            _insert(c)
    logger.info("laps_stored", ride_id=ride_id, lap_count=len(rows))


async def _download_rides(sync_id: str, log_lines: list[str], conn) -> tuple[int, int, str | None]:
    """Download rides from intervals.icu that we don't already have.

    Returns (downloaded, skipped, earliest_new_ride_date).
    """
    t0 = time.monotonic()
    downloaded = 0
    skipped = 0
    earliest_date: str | None = None

    # Determine date range from watermark
    _tz = _get_athlete_tz()
    watermark = get_watermark("rides_newest", conn=conn)
    if watermark:
        # Re-fetch from watermark date (not day after) — a ride may have been
        # uploaded to intervals.icu after the sync that set the watermark.
        # Dedup logic handles any rides we already have.
        oldest = datetime.fromisoformat(watermark).strftime("%Y-%m-%d")
    else:
        oldest = (datetime.now(_tz) - timedelta(days=365)).strftime("%Y-%m-%d")

    newest = datetime.now(_tz).strftime("%Y-%m-%d")

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
    # Fingerprint uses UTC date from start_time (sufficient for cross-source dedup;
    # at most one day off for rides near midnight UTC which is acceptable).
    existing_filenames = set()
    existing_fingerprints = set()
    rows = conn.execute("SELECT filename, start_time, distance_m FROM rides").fetchall()
    for r in rows:
        row = dict(r)
        existing_filenames.add(row["filename"])
        # Fingerprint: (UTC date from start_time, distance rounded to nearest 100m)
        st = row.get("start_time")
        date_str = st.strftime("%Y-%m-%d") if hasattr(st, "strftime") else (str(st)[:10] if st else "")
        dist = round((row["distance_m"] or 0) / 100) * 100
        existing_fingerprints.add((date_str, dist))

    # Early exit: check if all activities already exist locally
    has_new = False
    for activity in activities:
        ride = map_activity_to_ride(activity)
        if ride is None:
            continue
        if ride["filename"] in existing_filenames:
            continue
        dist = round((ride["distance_m"] or 0) / 100) * 100
        rd = ride["start_time"][:10] if ride.get("start_time") else ""
        if (rd, dist) in existing_fingerprints:
            continue
        has_new = True
        break
    if not has_new:
        msg = f"All {len(activities)} activities already synced"
        logger.info(msg)
        log_lines.append(_tlog(msg))
        await _broadcast(sync_id, {"phase": "rides", "detail": msg})
        set_watermark("rides_newest", newest, conn=conn)
        logger.info("ride_download_complete", rides_downloaded=0, rides_skipped=len(activities),
                    latency_s=round(time.monotonic() - t0, 1))
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
        ride_date_str = ride["start_time"][:10] if ride.get("start_time") else ""
        dist = round((ride["distance_m"] or 0) / 100) * 100
        fingerprint = (ride_date_str, dist)
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
            if earliest_date is None or ride_date_str < earliest_date:
                earliest_date = ride_date_str
            detail = f"Downloaded ride: {ride_date_str} ({ride.get('sport', 'ride')})"
            logger.info(detail)
            log_lines.append(_tlog(detail))

            # Fetch and store per-second stream data
            if ride_db_id:
                icu_id = activity.get("id", "")
                sport = ride.get("sport", "").lower()
                is_cycling = sport in ('ride', 'ebikeride', 'emountainbikeride', 'gravelride', 'mountainbikeride', 'trackride', 'velomobile', 'virtualride', 'handcycle', 'cycling')
                stream_map = {}
                try:
                    t_stream = time.monotonic()
                    streams = await asyncio.to_thread(fetch_activity_streams, icu_id)
                    if streams:
                        _store_streams(ride_db_id, streams, conn=conn)
                        # Backfill start_lat/start_lon from stream GPS data
                        _backfill_start_location(ride_db_id, streams, conn=conn)
                        log_lines.append(_tlog(f"  + stored stream data for {ride_date_str} ({(time.monotonic()-t_stream)*1000:.0f}ms)"))

                        # Step 3.A: Process ride samples for metrics and power bests
                        stream_map = _extract_streams(streams)
                        raw_powers = stream_map.get("watts", []) if is_cycling else []
                        raw_hrs = stream_map.get("heartrate", [])
                        raw_cadences = stream_map.get("cadence", [])

                        # Fetch HR benchmarks for hrTSS fallback
                        ride_date = ride_date_str
                        lthr = get_latest_metric(conn, "lthr", ride_date)
                        max_hr_setting = get_latest_metric(conn, "max_hr", ride_date)
                        resting_hr = get_latest_metric(conn, "resting_hr", ride_date)

                        # Use same logic as ingest.py for FTP
                        from server.ingest import get_benchmark_for_date
                        ftp = get_benchmark_for_date(conn, "ftp", ride_date)
                        if ftp <= 0:
                            ftp = ride.get("ftp") or 0

                        metrics = await asyncio.to_thread(
                            process_ride_samples,
                            raw_powers,
                            raw_hrs,
                            raw_cadences,
                            ftp,
                            ride["duration_s"],
                            lthr=lthr,
                            max_hr=max_hr_setting,
                            resting_hr=resting_hr,
                        )

                        # Step 3.B: Persist the calculated metrics
                        if metrics["has_power_data"]:
                            pb_map = {pb["duration_s"]: pb["power"] for pb in metrics["power_bests"]}
                            conn.execute(
                                """UPDATE rides SET 
                                   normalized_power = ?, tss = ?, intensity_factor = ?, variability_index = ?,
                                   avg_power = ?, avg_hr = ?, avg_cadence = ?,
                                   best_1min_power = ?, best_5min_power = ?, best_20min_power = ?, best_60min_power = ?,
                                   has_power_data = ?, data_status = ?
                                   WHERE id = ?""",
                                (
                                    metrics["np_power"],
                                    metrics["tss"],
                                    metrics["intensity_factor"],
                                    metrics["variability_index"],
                                    metrics["avg_power"],
                                    metrics["avg_hr"],
                                    metrics["avg_cadence"],
                                    pb_map.get(60),
                                    pb_map.get(300),
                                    pb_map.get(1200),
                                    pb_map.get(3600),
                                    True,
                                    metrics["data_status"],
                                    ride_db_id,
                                ),
                            )
                        else:
                            # Still update avg_hr and avg_cadence even if no power, and clear power metrics
                            conn.execute(
                                """UPDATE rides SET 
                                   avg_hr = ?, avg_cadence = ?,
                                   normalized_power = NULL, avg_power = NULL, max_power = NULL,
                                   intensity_factor = NULL, variability_index = NULL,
                                   best_1min_power = NULL, best_5min_power = NULL, best_20min_power = NULL, best_60min_power = NULL,
                                   has_power_data = FALSE, data_status = ?
                                   WHERE id = ?""",
                                (metrics["avg_hr"], metrics["avg_cadence"], metrics["data_status"], ride_db_id),
                            )
                            if metrics["tss"] > 0:
                                # hrTSS fallback
                                conn.execute(
                                    "UPDATE rides SET tss = ? WHERE id = ?",
                                    (metrics["tss"], ride_db_id),
                                )

                        # Insert all power bests (date is UTC-derived from start_time)
                        if metrics["power_bests"]:
                            pb_date = ride_date_str
                            conn.executemany(
                                "INSERT INTO power_bests (ride_id, date, duration_s, power, avg_hr, avg_cadence, start_offset_s) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                [
                                    (
                                        ride_db_id,
                                        pb_date,
                                        pb["duration_s"],
                                        pb["power"],
                                        pb.get("avg_hr"),
                                        pb.get("avg_cadence"),
                                        pb.get("start_offset_s"),
                                    )
                                    for pb in metrics["power_bests"]
                                ],
                            )
                        log_lines.append(_tlog(f"  + calculated metrics and {len(metrics['power_bests'])} power bests"))
                except Exception as se:
                    err = f"Could not fetch or process streams for {icu_id}: {se}"
                    logger.warning("streams_fetch_failed", icu_id=icu_id, error=str(se))
                    log_lines.append(_tlog(f"  ! {err}"))

                # Fetch and store device laps from FIT file
                try:
                    laps = await asyncio.to_thread(fetch_activity_fit_laps, icu_id)
                    if laps:
                        # Calculate NP per lap from stream power data
                        if is_cycling and stream_map:
                            _enrich_laps_with_np(laps, stream_map)
                        _store_laps(ride_db_id, laps, conn=conn)
                        log_lines.append(_tlog(f"  + stored {len(laps)} laps for {ride_date_str}"))
                except Exception as le:
                    logger.warning("laps_fetch_failed", icu_id=icu_id, error=str(le))

        except Exception as e:
            err = f"Error inserting ride {ride['filename']}: {e}"
            logger.error("ride_insert_failed", filename=ride["filename"], error=str(e), exc_info=e)
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

    logger.info("ride_download_complete", rides_downloaded=downloaded, rides_skipped=skipped,
                latency_s=round(time.monotonic() - t0, 1))
    return downloaded, skipped, earliest_date


async def _download_planned_workouts(sync_id: str, log_lines: list[str], conn) -> int:
    """Download planned workouts from intervals.icu calendar that don't exist locally.

    This handles the case where workouts were created on intervals.icu directly
    (or when the local DB is rebuilt from scratch).  Only inserts rows that
    don't already exist in planned_workouts; never overwrites local data.

    Returns the number of workouts imported.
    """
    t0 = time.monotonic()
    _tz = _get_athlete_tz()
    _now_local = datetime.now(_tz)
    today = _now_local.strftime("%Y-%m-%d")
    end_date = (_now_local + timedelta(days=28)).strftime("%Y-%m-%d")

    msg = f"Checking intervals.icu for planned workouts ({today} to {end_date})..."
    logger.info(msg)
    log_lines.append(_tlog(msg))
    await _broadcast(sync_id, {"phase": "workouts_download", "detail": msg})

    try:
        raw_events = await asyncio.to_thread(fetch_calendar_events, today, end_date)
    except Exception as e:
        log_lines.append(_tlog(f"Could not fetch calendar events from intervals.icu: {e}"))
        return 0

    if not raw_events:
        log_lines.append(_tlog("No upcoming calendar events on intervals.icu"))
        return 0

    # Build a set of (date, name) pairs already in the local DB so we don't duplicate.
    # Use str() on date since planned_workouts.date is DATE type (returns
    # datetime.date) but event_date from intervals.icu API is a string.
    existing = set()
    for row in conn.execute(
        "SELECT date, name FROM planned_workouts WHERE date >= ?", (today,)
    ).fetchall():
        r = dict(row)
        existing.add((str(r["date"]), r["name"] or ""))

    imported = 0
    for event in raw_events:
        if event.get("category") != "WORKOUT":
            continue
        event_date = (event.get("start_date_local") or "")[:10]
        if not event_date or event_date < today:
            continue

        name = event.get("name") or "Workout"
        if (event_date, name) in existing:
            continue

        # Map the intervals.icu event into a planned_workouts row.
        # file_contents holds the ZWO XML if a workout file was attached.
        workout_xml = event.get("file_contents") or None
        description = event.get("description") or None
        moving_time = event.get("moving_time") or None
        icu_event_id = event.get("id")

        try:
            conn.execute(
                "INSERT INTO planned_workouts (date, name, workout_xml, coach_notes, total_duration_s, icu_event_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (event_date, name, workout_xml, description, moving_time, icu_event_id),
            )
            existing.add((event_date, name))
            imported += 1
            log_lines.append(_tlog(f"Imported planned workout from intervals.icu: {event_date} {name}"))
        except Exception as e:
            logger.warning("calendar_event_import_failed", name=name, date=event_date, error=str(e))

    logger.info("workout_download_complete", imported=imported, latency_s=round(time.monotonic() - t0, 1))
    return imported


async def _upload_workouts(sync_id: str, log_lines: list[str], conn) -> tuple[int, int]:
    """Upload planned workouts to intervals.icu that haven't been synced yet."""
    t0 = time.monotonic()
    uploaded = 0
    skipped = 0

    # Get watermark - tracks the newest date we've synced workouts for
    watermark = get_watermark("workouts_synced_through", conn=conn)
    _tz = _get_athlete_tz()
    _now_local = datetime.now(_tz)
    today = _now_local.strftime("%Y-%m-%d")

    # Only sync workouts from today onward (no point syncing past workouts)
    start_date = today
    # Look ahead 4 weeks
    end_date = (_now_local + timedelta(days=28)).strftime("%Y-%m-%d")

    msg = f"Checking workouts to sync: {start_date} to {end_date}"
    logger.info(msg)
    log_lines.append(_tlog(msg))
    await _broadcast(sync_id, {"phase": "workouts", "detail": msg})

    # Get our planned workouts with XML and sync tracking columns
    local_workouts = conn.execute(
        "SELECT id, date, name, workout_xml, total_duration_s, icu_event_id, sync_hash FROM planned_workouts "
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

    # Batch-fetch all existing Intervals.icu events for the date range up front.
    # This avoids N separate API calls (one per workout) to check for duplicates.
    icu_events_by_date: dict[str, list[dict]] = {}
    try:
        raw_events = await asyncio.to_thread(fetch_calendar_events, start_date, end_date)
        for event in raw_events:
            if event.get("category") != "WORKOUT":
                continue
            event_date = (event.get("start_date_local") or "")[:10]
            if event_date:
                icu_events_by_date.setdefault(event_date, []).append(event)
        log_lines.append(_tlog(f"Fetched {len(raw_events)} existing Intervals.icu events for date range"))
    except Exception as e:
        log_lines.append(_tlog(f"Warning: could not prefetch Intervals.icu events ({e}); will attempt push without dedup"))

    def _find_event_id(date: str, name: str) -> int | None:
        """Look up an existing Intervals.icu event id from the prefetched cache."""
        for event in icu_events_by_date.get(date, []):
            if event.get("name") == name:
                return event.get("id")
        return None

    now_iso = _now_iso()

    for i, w in enumerate(local_workouts):
        w = dict(w)
        w_date = str(w["date"])
        w_name = w["name"] or "Workout"
        moving_time = int(w.get("total_duration_s") or 0)

        # Hash-based dedup: skip if unchanged and already synced
        current_hash = compute_sync_hash(w_name, w_date, w["workout_xml"], moving_time)
        icu_event_id = w.get("icu_event_id")

        if w.get("sync_hash") == current_hash and icu_event_id:
            skipped += 1
            detail = f"Skipped (unchanged): {w_date} {w_name}"
            logger.info(detail)
            log_lines.append(_tlog(detail))
            continue

        # Check the prefetched event cache for an existing event (no extra API call)
        if not icu_event_id:
            icu_event_id = _find_event_id(w_date, w_name)
            if icu_event_id:
                logger.info("Found existing Intervals.icu event %s matching '%s' on %s", icu_event_id, w_name, w_date)

        try:
            result = await asyncio.to_thread(
                push_workout,
                date=w_date,
                name=w_name,
                zwo_xml=w["workout_xml"],
                moving_time_secs=moving_time,
                icu_event_id=icu_event_id,
            )
            if result.get("status") == "success":
                uploaded += 1
                # Store event_id and hash for future dedup
                conn.execute(
                    "UPDATE planned_workouts SET icu_event_id = ?, sync_hash = ?, synced_at = ? WHERE id = ?",
                    (result.get("event_id"), current_hash, now_iso, w["id"]),
                )
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

    logger.info("workout_upload_complete", uploaded=uploaded, skipped=skipped,
                latency_s=round(time.monotonic() - t0, 1))
    return uploaded, skipped


def backfill_laps_from_icu() -> dict:
    """Backfill lap data from intervals.icu for rides that don't have laps yet."""
    with get_db() as conn:
        rides_with_laps = set(
            r["ride_id"] for r in conn.execute("SELECT DISTINCT ride_id FROM ride_laps").fetchall()
        )
        icu_rides = conn.execute(
            "SELECT id, filename FROM rides WHERE filename LIKE 'icu_%'"
        ).fetchall()

    backfilled = 0
    errors = 0
    for ride in icu_rides:
        if ride["id"] in rides_with_laps:
            continue
        icu_id = ride["filename"].replace("icu_", "")
        try:
            laps = fetch_activity_fit_laps(icu_id)
            if laps:
                _store_laps(ride["id"], laps)
                backfilled += 1
        except Exception as e:
            logger.warning("laps_backfill_failed", filename=ride["filename"], error=str(e))
            errors += 1

    return {"backfilled": backfilled, "skipped": len(icu_rides) - backfilled - errors, "errors": errors}


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
    rides_dl = rides_skip = wo_dl = wo_up = wo_skip = 0

    try:
        with get_db() as conn:
            _create_sync_run(sync_id, conn=conn)
            conn.commit()

            await _broadcast(sync_id, {"status": "running", "phase": "rides", "detail": "Starting ride download..."})

            # Phase 1: Download rides
            rides_dl, rides_skip, earliest = await _download_rides(sync_id, log_lines, conn)
            if rides_dl > 0:
                from server.ingest import sync_athlete_settings_from_latest_ride
                sync_athlete_settings_from_latest_ride(conn)
            conn.commit()

            await _broadcast(sync_id, {"status": "running", "phase": "workouts_download", "detail": "Checking intervals.icu for incoming planned workouts..."})

            # Phase 2: Download any planned workouts from intervals.icu that
            # don't exist locally (e.g. created on intervals.icu directly, or
            # after a DB rebuild).
            wo_dl = await _download_planned_workouts(sync_id, log_lines, conn)
            conn.commit()

            await _broadcast(sync_id, {"status": "running", "phase": "workouts", "detail": "Starting workout upload..."})

            # Phase 3: Upload workouts
            wo_up, wo_skip = await _upload_workouts(sync_id, log_lines, conn)
            conn.commit()

            # Phase 4: Recompute PMC if we downloaded new rides
            if rides_dl > 0:
                msg = "Recomputing daily metrics (PMC)..."
                log_lines.append(_tlog(msg))
                await _broadcast(sync_id, {"phase": "pmc", "detail": msg})
                try:
                    from server.ingest import compute_daily_pmc
                    compute_daily_pmc(conn, since_date=earliest, tz_name="UTC")
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
                f"{wo_dl} planned workouts imported, {wo_up} uploaded, {wo_skip} skipped"
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
        logger.error("sync_failed", sync_id=sync_id, error=str(e), exc_info=e)
        log_lines.append(_tlog(err))
        errors.append(str(e))
        rides_dl = rides_skip = wo_dl = wo_up = wo_skip = 0

        # Persist failure state with a fresh connection.  Wrapped in its own
        # try/except so a secondary DB failure can't prevent _broadcast below.
        try:
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
        except Exception as db_err:
            logger.error("sync_state_persist_failed", sync_id=sync_id, error=str(db_err))

    final_msg = {
        "status": status,
        "sync_id": sync_id,
        "rides_downloaded": rides_dl,
        "rides_skipped": rides_skip,
        "workouts_downloaded": wo_dl,
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

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_sync(sync_id))
    except RuntimeError:
        asyncio.run(run_sync(sync_id))

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

def sync_single_ride_background(icu_id: str) -> str:
    sync_id = str(uuid.uuid4())[:8]
    _create_sync_run(sync_id)

    async def _run():
        try:
            logger.info("single_ride_sync_start", icu_id=icu_id, sync_id=sync_id)
            from server.services.single_sync import import_specific_activity
            await import_specific_activity(icu_id)
        except Exception as e:
            logger.error("single_ride_sync_failed", icu_id=icu_id, sync_id=sync_id, exc_info=True)
            _update_sync_run(sync_id, status="failed", errors=str(e), completed_at=_now_iso())
        else:
            _update_sync_run(sync_id, status="completed", log=f"Successfully re-synced {icu_id}", completed_at=_now_iso())

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())

    return sync_id
