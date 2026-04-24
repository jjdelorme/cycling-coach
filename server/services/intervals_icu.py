"""intervals.icu API integration for syncing workouts and downloading rides."""

import contextlib
import hashlib
import os
import tempfile
from datetime import datetime, timedelta, timezone
import fitparse
import httpx

from server.config import INTERVALS_ICU_API_KEY, INTERVALS_ICU_ATHLETE_ID, INTERVALS_ICU_DISABLED
from server.logging_config import get_logger

logger = get_logger(__name__)

BASE_URL = "https://intervals.icu"


def compute_sync_hash(name: str, date: str, zwo_xml: str, moving_time_secs: int = 0) -> str:
    """Compute a hash for deduplication of workout syncs."""
    content = f"{date}|{name}|{moving_time_secs}|{zwo_xml}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _get_credentials() -> tuple[str, str]:
    """Get intervals.icu credentials from DB settings, falling back to env vars."""
    from server.database import get_setting
    api_key = get_setting("intervals_icu_api_key") or INTERVALS_ICU_API_KEY
    athlete_id = get_setting("intervals_icu_athlete_id") or INTERVALS_ICU_ATHLETE_ID
    return api_key, athlete_id


def is_configured() -> bool:
    api_key, athlete_id = _get_credentials()
    return bool(api_key and athlete_id)


def is_sync_disabled() -> bool:
    return INTERVALS_ICU_DISABLED


def push_workout(
    date: str,
    name: str,
    zwo_xml: str,
    description: str = "",
    moving_time_secs: int = 0,
    icu_event_id: int | None = None,
) -> dict:
    """Push a planned workout to intervals.icu calendar.

    If icu_event_id is provided, updates the existing event (PUT).
    Otherwise creates a new event (POST).
    """
    if is_sync_disabled():
        return {"error": "Syncing is disabled via INTERVALS_ICU_DISABLE environment variable."}

    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        return {"error": "intervals.icu not configured. Set API key and Athlete ID in Settings."}

    payload = {
        "category": "WORKOUT",
        "start_date_local": date + "T00:00:00" if len(date) == 10 else date,
        "name": name,
        "description": description,
        "type": "Ride",
        "filename": name.lower().replace(" ", "_").replace("/", "_") + ".zwo",
        "file_contents": zwo_xml,
    }
    if moving_time_secs > 0:
        payload["moving_time"] = moving_time_secs

    if icu_event_id:
        # Update existing event
        url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/events/{icu_event_id}"
        resp = httpx.put(url, json=payload, auth=("API_KEY", api_key), timeout=15.0)
    else:
        # Create new event
        url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/events"
        resp = httpx.post(url, json=payload, auth=("API_KEY", api_key), timeout=15.0)

    if resp.status_code in (200, 201):
        event_data = resp.json()
        return {"status": "success", "event_id": event_data.get("id"), "event": event_data}
    else:
        logger.error("icu_push_failed", status=resp.status_code, body=resp.text[:200])
        return {
            "status": "error",
            "code": resp.status_code,
            "message": resp.text[:500],
        }


def push_workouts_bulk(workouts: list[dict]) -> dict:
    """Push multiple planned workouts to intervals.icu calendar."""
    if is_sync_disabled():
        return {"error": "Syncing is disabled via INTERVALS_ICU_DISABLE environment variable."}

    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        return {"error": "intervals.icu not configured. Set API key and Athlete ID in Settings."}

    url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/events/bulk"

    events = []
    for w in workouts:
        event = {
            "category": "WORKOUT",
            "start_date_local": str(w["date"]) + "T00:00:00" if len(str(w["date"])) == 10 else str(w["date"]),
            "name": w["name"],
            "description": w.get("description", ""),
            "type": "Ride",
            "filename": w["name"].lower().replace(" ", "_").replace("/", "_") + ".zwo",
            "file_contents": w["zwo_xml"],
        }
        if w.get("moving_time_secs", 0) > 0:
            event["moving_time"] = w["moving_time_secs"]
        events.append(event)

    resp = httpx.post(
        url,
        json=events,
        auth=("API_KEY", api_key),
        timeout=30.0,
    )

    if resp.status_code in (200, 201):
        return {"status": "success", "count": len(events), "events": resp.json()}
    else:
        return {
            "status": "error",
            "code": resp.status_code,
            "message": resp.text[:500],
        }


def delete_event(event_id: int) -> dict:
    """Delete an event from intervals.icu calendar."""
    if is_sync_disabled():
        return {"error": "Syncing is disabled via INTERVALS_ICU_DISABLE environment variable."}

    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        return {"status": "error", "message": "intervals.icu not configured"}

    url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/events/{event_id}"
    resp = httpx.delete(url, auth=("API_KEY", api_key), timeout=15.0)

    if resp.status_code in (200, 204):
        return {"status": "success"}
    else:
        logger.warning("icu_delete_failed", event_id=event_id, status=resp.status_code)
        return {"status": "error", "code": resp.status_code, "message": resp.text[:500]}


def fetch_activities(oldest: str | None = None, newest: str | None = None) -> list[dict]:
    """Fetch activities from intervals.icu.

    Args:
        oldest: Start date (YYYY-MM-DD). Defaults to 90 days ago.
        newest: End date (YYYY-MM-DD). Defaults to today.

    Returns:
        List of activity dicts from intervals.icu API.
    """
    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        raise RuntimeError("intervals.icu not configured")

    if not oldest:
        oldest = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    if not newest:
        newest = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/activities"
    params = {"oldest": oldest, "newest": newest}

    logger.info("icu_fetch_activities", oldest=oldest, newest=newest)
    resp = httpx.get(url, params=params, auth=("API_KEY", api_key), timeout=30.0)

    if resp.status_code != 200:
        logger.error("icu_fetch_activities_failed", status=resp.status_code, body=resp.text[:200])
        raise RuntimeError(f"intervals.icu API error {resp.status_code}: {resp.text[:300]}")

    activities = resp.json()
    logger.info("icu_activities_fetched", count=len(activities), oldest=oldest, newest=newest)
    return activities


def fetch_activity_streams(activity_id: str) -> dict:
    """Fetch per-second stream data for an activity (power, hr, etc.).

    Returns dict with keys like 'time', 'watts', 'heartrate', 'cadence', etc.
    """
    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        raise RuntimeError("intervals.icu not configured")

    url = f"{BASE_URL}/api/v1/activity/{activity_id}/streams"
    params = {"types": "time,watts,heartrate,cadence,velocity_smooth,altitude,distance,latlng"}

    resp = httpx.get(url, params=params, auth=("API_KEY", api_key), timeout=30.0)

    if resp.status_code != 200:
        logger.error("icu_fetch_streams_failed", activity_id=activity_id, status=resp.status_code)
        return {}

    return resp.json()



def _semicircles_to_degrees(val):
    """Convert Garmin semicircle coordinates to decimal degrees, or return None."""
    if val is None:
        return None
    if abs(val) > 180:
        return val * (180 / 2**31)
    return val



@contextlib.contextmanager
def _open_fit(activity_id: str):
    """Download the intervals.icu FIT file and yield a parsed ``fitparse.FitFile``.

    The download + tempfile + parse + cleanup dance is identical for every
    consumer (laps and per-record GPS), so it lives in one place. Yields:

        * ``fitparse.FitFile`` instance when the download succeeded and the
          file parsed cleanly.
        * ``None`` when the download returned non-200 OR ``fitparse`` raised
          (logged at WARNING). Callers should handle ``None`` by returning
          their empty-list sentinel.

    The temp file is always unlinked on exit, even on parse failure.
    """
    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        raise RuntimeError("intervals.icu not configured")

    url = f"{BASE_URL}/api/v1/activity/{activity_id}/file"
    resp = httpx.get(url, auth=("API_KEY", api_key), timeout=60.0)

    if resp.status_code != 200:
        logger.warning(
            "icu_fit_download_failed",
            activity_id=activity_id,
            status=resp.status_code,
        )
        yield None
        return

    fd, tmp_path = tempfile.mkstemp(suffix=".fit")
    fitfile = None
    try:
        os.write(fd, resp.content)
        os.close(fd)
        try:
            fitfile = fitparse.FitFile(tmp_path)
        except Exception as e:
            logger.warning(
                "icu_fit_parse_failed", activity_id=activity_id, error=str(e)
            )
            fitfile = None
        yield fitfile
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _lap_messages_to_dicts(activity_id: str, fit_laps) -> list[dict]:
    """Convert fitparse ``lap`` messages into the flat dicts our DB consumes.

    Extracted so ``fetch_activity_fit_laps`` and ``fetch_activity_fit_all``
    (Phase 9 dedup) can share the same projection logic — only the FIT
    download/open is different between them.
    """
    laps = []
    for i, lap in enumerate(fit_laps):
        fields = {f.name: f.value for f in lap.fields}

        intensity = fields.get("intensity")
        if not isinstance(intensity, str):
            intensity = None

        lap_trigger = fields.get("lap_trigger")
        if not isinstance(lap_trigger, str):
            lap_trigger = None

        laps.append({
            "lap_index": fields.get("message_index", i),
            "start_time": str(fields["start_time"]) if fields.get("start_time") else None,
            "total_timer_time": fields.get("total_timer_time"),
            "total_elapsed_time": fields.get("total_elapsed_time"),
            "total_distance": fields.get("total_distance"),
            "avg_power": fields.get("avg_power"),
            "normalized_power": fields.get("Normalized Power"),
            "max_power": fields.get("max_power"),
            "avg_hr": fields.get("avg_heart_rate"),
            "max_hr": fields.get("max_heart_rate"),
            "avg_cadence": fields.get("avg_cadence"),
            "max_cadence": fields.get("max_cadence"),
            "avg_speed": fields.get("enhanced_avg_speed"),
            "max_speed": fields.get("enhanced_max_speed"),
            "total_ascent": fields.get("total_ascent"),
            "total_descent": fields.get("total_descent"),
            "total_calories": fields.get("total_calories"),
            "total_work": fields.get("total_work"),
            "intensity": intensity,
            "lap_trigger": lap_trigger,
            "wkt_step_index": fields.get("wkt_step_index"),
            "start_lat": _semicircles_to_degrees(fields.get("start_position_lat")),
            "start_lon": _semicircles_to_degrees(fields.get("start_position_long")),
            "end_lat": _semicircles_to_degrees(fields.get("end_position_lat")),
            "end_lon": _semicircles_to_degrees(fields.get("end_position_long")),
            "avg_temperature": fields.get("avg_temperature"),
        })

    logger.info("icu_fit_laps_extracted", activity_id=activity_id, lap_count=len(laps))
    return laps


def fetch_activity_fit_laps(activity_id: str) -> list[dict]:
    """Download the original FIT file from intervals.icu and extract device laps.

    Returns the actual device-recorded laps (e.g. manual lap presses on a Garmin)
    by parsing the original FIT file.
    """
    with _open_fit(activity_id) as fitfile:
        if fitfile is None:
            return []
        try:
            fit_laps = list(fitfile.get_messages("lap"))
        except Exception as e:
            logger.warning(
                "icu_fit_parse_failed", activity_id=activity_id, error=str(e)
            )
            return []

    return _lap_messages_to_dicts(activity_id, fit_laps)


def _fit_timestamp_to_iso_utc(value) -> str | None:
    """Convert a fitparse ``record.timestamp`` value to an ISO-8601 UTC string.

    fitparse usually returns a ``datetime`` (the FIT spec stores timestamps
    as seconds since the FIT epoch in UTC). Some malformed files have
    naive datetimes; we explicitly tag those with UTC rather than emitting
    a timezone-less ISO string. Returns ``None`` when the value is missing
    or not a recognised type.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat()
    if isinstance(value, str):
        # Already a string — pass through; the downstream column is TEXT.
        return value
    return None


def _record_messages_to_dicts(activity_id: str, fit_records) -> list[dict]:
    """Convert fitparse ``record`` messages into the flat dicts our DB consumes.

    Extracted so ``fetch_activity_fit_records`` and
    ``fetch_activity_fit_all`` (Phase 9 dedup) share the same projection
    logic — only the FIT download/open is different between them.
    """
    records: list[dict] = []
    for msg in fit_records:
        fields = {f.name: f.value for f in msg.fields}

        ts = _fit_timestamp_to_iso_utc(fields.get("timestamp"))
        if ts is None:
            # Defensive: a record with no timestamp is unusable downstream
            # (no way to align it with the time-series in metrics).
            continue

        speed = fields.get("enhanced_speed")
        if speed is None:
            speed = fields.get("speed")

        altitude = fields.get("enhanced_altitude")
        if altitude is None:
            altitude = fields.get("altitude")

        records.append(
            {
                "timestamp_utc": ts,
                "power": fields.get("power"),
                "heart_rate": fields.get("heart_rate"),
                "cadence": fields.get("cadence"),
                "speed": speed,
                "altitude": altitude,
                "distance": fields.get("distance"),
                "lat": _semicircles_to_degrees(fields.get("position_lat")),
                "lon": _semicircles_to_degrees(fields.get("position_long")),
                "temperature": fields.get("temperature"),
            }
        )

    logger.info(
        "icu_fit_records_extracted",
        activity_id=activity_id,
        record_count=len(records),
    )
    return records


def fetch_activity_fit_records(activity_id: str) -> list[dict]:
    """Download the intervals.icu FIT file and extract per-second ``record`` messages.

    Returns a list of dicts in the same flat shape ``parse_ride_json`` builds
    today, ready for ``_store_records_from_fit`` (Phase 6) to consume::

        {
            "timestamp_utc": str | None,  # ISO-8601 UTC
            "power":         int | None,
            "heart_rate":    int | None,
            "cadence":       int | None,
            "speed":         float | None,  # m/s, raw (smoothed in Phase 8)
            "altitude":      float | None,  # m
            "distance":      float | None,  # m
            "lat":           float | None,  # degrees
            "lon":           float | None,  # degrees
            "temperature":   float | None,
        }

    Field-source rules (Campaign 20 D1):
      * ``speed``    = ``record.enhanced_speed`` ?? ``record.speed``
      * ``altitude`` = ``record.enhanced_altitude`` ?? ``record.altitude``
      * ``lat``/``lon`` are converted from semicircles via
        ``_semicircles_to_degrees``.

    Returns ``[]`` (never raises) when:
      * the FIT file is unavailable (non-200),
      * ``fitparse`` throws while opening the file, or
      * the file contains zero ``record`` messages.

    Records that are missing a ``timestamp`` field are skipped defensively
    (extremely rare in practice).
    """
    with _open_fit(activity_id) as fitfile:
        if fitfile is None:
            return []
        try:
            fit_records = list(fitfile.get_messages("record"))
        except fitparse.FitParseError as e:
            logger.warning(
                "icu_fit_parse_failed", activity_id=activity_id, error=str(e)
            )
            return []
        except Exception as e:
            logger.warning(
                "icu_fit_parse_failed", activity_id=activity_id, error=str(e)
            )
            return []

    return _record_messages_to_dicts(activity_id, fit_records)


def fetch_activity_fit_all(activity_id: str) -> dict:
    """Download the intervals.icu FIT file once; return both lap and record extracts.

    The same FIT file is parsed twice (once for ``lap`` messages, once for
    ``record`` messages) but downloaded only once via ``_open_fit``. Saves
    one HTTP round-trip per ride compared with calling
    ``fetch_activity_fit_laps`` and ``fetch_activity_fit_records``
    back-to-back — the perf cost compounds on the bulk-sync hot path and
    on the Phase 9 backfill sweep, where this helper is the call site.

    Returns:
        ``{"laps": list[dict], "records": list[dict]}`` — both lists
        have the same shape the single-purpose helpers emit. On any
        download or parse failure the helper returns
        ``{"laps": [], "records": []}`` (matches the empty-list sentinel
        both single-purpose helpers already use).
    """
    with _open_fit(activity_id) as fitfile:
        if fitfile is None:
            return {"laps": [], "records": []}
        try:
            fit_laps = list(fitfile.get_messages("lap"))
        except Exception as e:  # noqa: BLE001 — fitparse can raise many shapes
            logger.warning(
                "icu_fit_parse_failed", activity_id=activity_id, error=str(e)
            )
            fit_laps = []
        try:
            fit_records = list(fitfile.get_messages("record"))
        except fitparse.FitParseError as e:
            logger.warning(
                "icu_fit_parse_failed", activity_id=activity_id, error=str(e)
            )
            fit_records = []
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "icu_fit_parse_failed", activity_id=activity_id, error=str(e)
            )
            fit_records = []

    return {
        "laps": _lap_messages_to_dicts(activity_id, fit_laps),
        "records": _record_messages_to_dicts(activity_id, fit_records),
    }


def map_activity_to_ride(activity: dict) -> dict | None:
    """Map an intervals.icu activity to our rides table schema.

    Returns None if the activity doesn't have enough data to be useful.
    """
    # Prefer UTC start_date for storage; fall back to start_date_local for existence check.
    # intervals.icu follows the Strava convention: start_date = UTC, start_date_local = local.
    start_date_utc = activity.get("start_date")
    start_date_local = activity.get("start_date_local", "")
    if not start_date_utc and not start_date_local:
        return None

    # Store UTC timestamp in start_time (used for AT TIME ZONE queries).
    start_time_value = start_date_utc or start_date_local

    # Use the intervals.icu activity id as a stable filename for dedup
    icu_id = activity.get("id", "")
    if not icu_id:
        return None

    moving_time = activity.get("moving_time", 0) or activity.get("elapsed_time", 0) or 0
    distance = activity.get("distance", 0) or 0

    sport = (activity.get("type") or "cycling").lower()
    is_cycling = sport in ('ride', 'ebikeride', 'emountainbikeride', 'gravelride', 'mountainbikeride', 'trackride', 'velomobile', 'virtualride', 'handcycle', 'cycling')

    ride = {
        "start_time": start_time_value,
        "title": activity.get("name"),
        "filename": f"icu_{icu_id}",
        "sport": sport,
        "sub_sport": (activity.get("sub_type") or "").lower(),
        "duration_s": moving_time,
        "distance_m": distance,
        "avg_power": (activity.get("average_watts") or activity.get("icu_weighted_avg_watts")) if is_cycling else None,
        "normalized_power": activity.get("icu_weighted_avg_watts") if is_cycling else None,
        "max_power": activity.get("max_watts") if is_cycling else None,
        "avg_hr": activity.get("average_heartrate"),
        "max_hr": activity.get("max_heartrate"),
        "avg_cadence": activity.get("average_cadence"),
        "total_ascent": activity.get("total_elevation_gain"),
        "total_descent": None,
        "total_calories": activity.get("calories"),
        "tss": activity.get("icu_training_load"),
        "intensity_factor": activity.get("icu_intensity"),
        "ftp": activity.get("icu_ftp"),
        "total_work_kj": activity.get("total_work") if activity.get("total_work") else (
            round(moving_time * (activity.get("average_watts") or 0) / 1000, 1)
            if activity.get("average_watts") else None
        ),
        "training_effect": activity.get("icu_training_load"),
        "variability_index": None,
        "best_1min_power": None,
        "best_5min_power": None,
        "best_20min_power": None,
        "best_60min_power": None,
        "weight": activity.get("icu_weight"),
        "start_lat": None,
        "start_lon": None,
    }

    # Extract power bests from icu_power_curve if available
    power_curve = activity.get("icu_power_curve")
    if power_curve and isinstance(power_curve, list):
        # intervals.icu returns power curve as array indexed by seconds
        for secs, field in [(60, "best_1min_power"), (300, "best_5min_power"),
                            (1200, "best_20min_power"), (3600, "best_60min_power")]:
            if len(power_curve) > secs:
                ride[field] = power_curve[secs]

    # Variability index
    avg_p = ride["avg_power"]
    np_p = ride["normalized_power"]
    if avg_p and np_p and avg_p > 0:
        ride["variability_index"] = round(np_p / avg_p, 3)

    return ride


def update_ftp(ftp: int) -> dict:
    """Update athlete FTP on intervals.icu.
    Endpoint: PUT /api/v1/athlete/{athleteId}/sport-settings/Ride
    Payload: {"ftp": value}
    Note: Use 0 for {athleteId} per Intervals.icu API.
    """
    if is_sync_disabled():
        return {"error": "Syncing is disabled via INTERVALS_ICU_DISABLE environment variable."}

    api_key, _ = _get_credentials()
    if not api_key:
        return {"status": "error", "message": "intervals.icu not configured"}

    url = f"{BASE_URL}/api/v1/athlete/0/sport-settings/Ride"
    payload = {"ftp": ftp}
    resp = httpx.put(url, json=payload, auth=("API_KEY", api_key), timeout=15.0)

    if resp.status_code in (200, 201):
        return {"status": "success", "data": resp.json()}
    else:
        logger.error("icu_ftp_update_failed", status=resp.status_code, body=resp.text[:200])
        return {"status": "error", "code": resp.status_code, "message": resp.text[:500]}


def update_weight(weight: float, date: str = None) -> dict:
    """Update athlete weight on intervals.icu.
    Endpoint: PUT /api/v1/athlete/{athleteId}/wellness/{date}
    Payload: {"weight": value}
    Date Format: YYYY-MM-DD. Defaults to today.
    """
    if is_sync_disabled():
        return {"error": "Syncing is disabled via INTERVALS_ICU_DISABLE environment variable."}

    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        return {"status": "error", "message": "intervals.icu not configured"}

    if not date:
        from server.utils.dates import user_today
        date = user_today()

    url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/wellness/{date}"
    payload = {"weight": weight}
    resp = httpx.put(url, json=payload, auth=("API_KEY", api_key), timeout=15.0)

    if resp.status_code in (200, 201):
        return {"status": "success", "data": resp.json()}
    else:
        logger.error("icu_weight_update_failed", status=resp.status_code, body=resp.text[:200])
        return {"status": "error", "code": resp.status_code, "message": resp.text[:500]}


def fetch_calendar_events(oldest: str, newest: str, category: str = "WORKOUT") -> list[dict]:
    """Fetch calendar events (planned workouts) from intervals.icu."""
    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        raise RuntimeError("intervals.icu not configured")

    url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/events"
    params = {"oldest": oldest, "newest": newest, "category": category}

    resp = httpx.get(url, params=params, auth=("API_KEY", api_key), timeout=15.0)

    if resp.status_code != 200:
        logger.error("icu_fetch_events_failed", status=resp.status_code, body=resp.text[:200])
        raise RuntimeError(f"intervals.icu API error {resp.status_code}: {resp.text[:300]}")

    return resp.json()


def find_matching_workout(date: str, name: str) -> int | None:
    """Check Intervals.icu for an existing workout on the same date with the same name."""
    try:
        events = fetch_calendar_events(date, date)
        for event in events:
            # Check if it's a workout and has the same name
            # Intervals.icu returns ISO timestamps for start_date_local, so we check if it starts with the date
            if event.get("category") == "WORKOUT" and event.get("name") == name:
                start_date = event.get("start_date_local", "")
                if start_date.startswith(date):
                    return event.get("id")
    except Exception as e:
        logger.warning("icu_find_workout_failed", name=name, date=date, error=str(e))
    return None
