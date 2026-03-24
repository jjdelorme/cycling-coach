"""intervals.icu API integration for syncing workouts to Garmin."""

import httpx
from server.config import INTERVALS_ICU_API_KEY, INTERVALS_ICU_ATHLETE_ID

BASE_URL = "https://intervals.icu"


def is_configured() -> bool:
    return bool(INTERVALS_ICU_API_KEY and INTERVALS_ICU_ATHLETE_ID)


def push_workout(
    date: str,
    name: str,
    zwo_xml: str,
    description: str = "",
    moving_time_secs: int = 0,
) -> dict:
    """Push a planned workout to intervals.icu calendar.

    Args:
        date: Scheduled date (YYYY-MM-DD).
        name: Workout name.
        zwo_xml: ZWO XML content.
        description: Optional description.
        moving_time_secs: Optional planned duration in seconds.

    Returns:
        Response from intervals.icu API.
    """
    if not is_configured():
        return {"error": "intervals.icu not configured. Set INTERVALS_ICU_API_KEY and INTERVALS_ICU_ATHLETE_ID."}

    url = f"{BASE_URL}/api/v1/athlete/{INTERVALS_ICU_ATHLETE_ID}/events"

    payload = {
        "category": "WORKOUT",
        "start_date_local": date,
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
        auth=("API_KEY", INTERVALS_ICU_API_KEY),
        timeout=15.0,
    )

    if resp.status_code in (200, 201):
        return {"status": "success", "event": resp.json()}
    else:
        return {
            "status": "error",
            "code": resp.status_code,
            "message": resp.text[:500],
        }


def push_workouts_bulk(workouts: list[dict]) -> dict:
    """Push multiple planned workouts to intervals.icu calendar.

    Args:
        workouts: List of dicts with keys: date, name, zwo_xml, description, moving_time_secs.

    Returns:
        Summary of results.
    """
    if not is_configured():
        return {"error": "intervals.icu not configured. Set INTERVALS_ICU_API_KEY and INTERVALS_ICU_ATHLETE_ID."}

    url = f"{BASE_URL}/api/v1/athlete/{INTERVALS_ICU_ATHLETE_ID}/events/bulk"

    events = []
    for w in workouts:
        event = {
            "category": "WORKOUT",
            "start_date_local": w["date"],
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
        auth=("API_KEY", INTERVALS_ICU_API_KEY),
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
