"""intervals.icu API integration for syncing workouts to Garmin."""

import logging
import httpx

from server.config import INTERVALS_ICU_API_KEY, INTERVALS_ICU_ATHLETE_ID

logger = logging.getLogger(__name__)

BASE_URL = "https://intervals.icu"


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
) -> dict:
    """Push a planned workout to intervals.icu calendar."""
    api_key, athlete_id = _get_credentials()
    if not (api_key and athlete_id):
        return {"error": "intervals.icu not configured. Set API key and Athlete ID in Settings."}

    url = f"{BASE_URL}/api/v1/athlete/{athlete_id}/events"

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

    resp = httpx.post(
        url,
        json=payload,
        auth=("API_KEY", api_key),
        timeout=15.0,
    )

    if resp.status_code in (200, 201):
        return {"status": "success", "event": resp.json()}
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
