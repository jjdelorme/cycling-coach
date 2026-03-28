"""intervals.icu API integration for syncing workouts and downloading rides."""

import hashlib
import logging
from datetime import datetime, timedelta
import httpx

from server.config import INTERVALS_ICU_API_KEY, INTERVALS_ICU_ATHLETE_ID

logger = logging.getLogger(__name__)

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
        logger.error("intervals.icu sync failed: status=%s body=%s", resp.status_code, resp.text[:500])
        return {
            "status": "error",
            "code": resp.status_code,
            "message": resp.text[:500],
        }


def push_workouts_bulk(workouts: list[dict]) -> dict:
    """Push multiple planned workouts to intervals.icu calendar."""
    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        return {"error": "intervals.icu not configured. Set API key and Athlete ID in Settings."}

    url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/events/bulk"

    events = []
    for w in workouts:
        event = {
            "category": "WORKOUT",
            "start_date_local": w["date"] + "T00:00:00" if len(w["date"]) == 10 else w["date"],
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
    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        return {"status": "error", "message": "intervals.icu not configured"}

    url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/events/{event_id}"
    resp = httpx.delete(url, auth=("API_KEY", api_key), timeout=15.0)

    if resp.status_code in (200, 204):
        return {"status": "success"}
    else:
        logger.warning("Failed to delete event %d: status=%s", event_id, resp.status_code)
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
        oldest = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    if not newest:
        newest = datetime.now().strftime("%Y-%m-%d")

    url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/activities"
    params = {"oldest": oldest, "newest": newest}

    logger.info("Fetching activities from intervals.icu: %s to %s", oldest, newest)
    resp = httpx.get(url, params=params, auth=("API_KEY", api_key), timeout=30.0)

    if resp.status_code != 200:
        logger.error("Failed to fetch activities: status=%s body=%s", resp.status_code, resp.text[:500])
        raise RuntimeError(f"intervals.icu API error {resp.status_code}: {resp.text[:300]}")

    activities = resp.json()
    logger.info("Fetched %d activities from intervals.icu", len(activities))
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
        logger.error("Failed to fetch streams for %s: status=%s", activity_id, resp.status_code)
        return {}

    return resp.json()


def map_activity_to_ride(activity: dict) -> dict | None:
    """Map an intervals.icu activity to our rides table schema.

    Returns None if the activity doesn't have enough data to be useful.
    """
    start_date = activity.get("start_date_local", "")
    if not start_date:
        return None

    # intervals.icu uses ISO format; extract date portion
    date = start_date[:10] if len(start_date) >= 10 else start_date

    # Use the intervals.icu activity id as a stable filename for dedup
    icu_id = activity.get("id", "")
    if not icu_id:
        return None

    moving_time = activity.get("moving_time", 0) or activity.get("elapsed_time", 0) or 0
    distance = activity.get("distance", 0) or 0

    ride = {
        "date": date,
        "start_time": start_date,
        "filename": f"icu_{icu_id}",
        "sport": (activity.get("type") or "cycling").lower(),
        "sub_sport": (activity.get("sub_type") or "").lower(),
        "duration_s": moving_time,
        "distance_m": distance,
        "avg_power": activity.get("average_watts") or activity.get("icu_weighted_avg_watts"),
        "normalized_power": activity.get("icu_weighted_avg_watts"),
        "max_power": activity.get("max_watts"),
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


def fetch_calendar_events(oldest: str, newest: str, category: str = "WORKOUT") -> list[dict]:
    """Fetch calendar events (planned workouts) from intervals.icu."""
    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        raise RuntimeError("intervals.icu not configured")

    url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/events"
    params = {"oldest": oldest, "newest": newest, "category": category}

    resp = httpx.get(url, params=params, auth=("API_KEY", api_key), timeout=15.0)

    if resp.status_code != 200:
        logger.error("Failed to fetch events: status=%s body=%s", resp.status_code, resp.text[:500])
        raise RuntimeError(f"intervals.icu API error {resp.status_code}: {resp.text[:300]}")

    return resp.json()
