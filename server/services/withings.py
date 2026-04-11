"""Withings Health API integration for body weight measurements."""
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from server.config import WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET, WITHINGS_REDIRECT_URI
from server.database import get_db, get_setting, set_setting
from server.logging_config import get_logger
from server.services import intervals_icu

logger = get_logger(__name__)

_AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
_TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
_MEASURE_URL = "https://wbsapi.withings.net/measure"


def is_configured() -> bool:
    return bool(WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET)


def is_connected() -> bool:
    return bool(get_setting("withings_access_token"))


def get_auth_url(redirect_uri: str) -> str:
    state = secrets.token_urlsafe(16)
    set_setting("withings_oauth_state", state)
    params = {
        "response_type": "code",
        "client_id": WITHINGS_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": "user.metrics",
        "state": state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, state: str, redirect_uri: str) -> dict:
    stored_state = get_setting("withings_oauth_state")
    if state != stored_state:
        return {"status": "error", "message": "Invalid OAuth state — possible CSRF"}
    resp = httpx.post(_TOKEN_URL, data={
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": WITHINGS_CLIENT_ID,
        "client_secret": WITHINGS_CLIENT_SECRET,
        "code": code,
        "redirect_uri": redirect_uri,
    }, timeout=15.0)
    if resp.status_code != 200:
        logger.error("withings_exchange_http_error", status=resp.status_code)
        return {"status": "error", "message": f"HTTP {resp.status_code} from Withings"}
    body = resp.json()
    if body.get("status") != 0:
        return {"status": "error", "message": body.get("error", "Unknown error")}
    data = body["body"]
    expiry = int(time.time()) + data["expires_in"]
    set_setting("withings_access_token", data["access_token"])
    set_setting("withings_refresh_token", data["refresh_token"])
    set_setting("withings_token_expiry", str(expiry))
    set_setting("withings_user_id", str(data.get("userid", "")))
    set_setting("withings_oauth_state", "")
    logger.info("withings_connected", user_id=data.get("userid"))
    return {"status": "success"}


def _refresh_tokens() -> str:
    refresh_token = get_setting("withings_refresh_token")
    resp = httpx.post(_TOKEN_URL, data={
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": WITHINGS_CLIENT_ID,
        "client_secret": WITHINGS_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }, timeout=15.0)
    body = resp.json()
    if body.get("status") != 0:
        raise RuntimeError(f"Withings token refresh failed: {body.get('error')}")
    data = body["body"]
    expiry = int(time.time()) + data["expires_in"]
    set_setting("withings_access_token", data["access_token"])
    set_setting("withings_refresh_token", data["refresh_token"])
    set_setting("withings_token_expiry", str(expiry))
    return data["access_token"]


def _get_valid_access_token() -> str:
    if not is_connected():
        raise RuntimeError("Withings is not connected. Authorize first.")
    expiry_str = get_setting("withings_token_expiry")
    try:
        expiry = int(expiry_str) if expiry_str else 0
    except ValueError:
        expiry = 0
    if time.time() >= expiry - 300:
        return _refresh_tokens()
    return get_setting("withings_access_token")


def _decode_weight(value: int, unit: int) -> float:
    return value * (10 ** unit)


def fetch_weight_measurements(start_date: str, end_date: str) -> list[dict]:
    token = _get_valid_access_token()
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_ts = int((datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).timestamp())
    resp = httpx.post(_MEASURE_URL, data={
        "action": "getmeas",
        "meastype": 1,
        "category": 1,  # 1=real measurements only, excludes Withings goal/objective entries
        "startdate": start_ts,
        "enddate": end_ts,
    }, headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
    body = resp.json()
    if body.get("status") != 0:
        logger.error("withings_measure_failed", status=body.get("status"))
        return []
    results = []
    for grp in body.get("body", {}).get("measuregrps", []):
        ts = grp["date"]
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        date_str = dt_utc.strftime("%Y-%m-%d")
        measured_at = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        for m in grp.get("measures", []):
            if m.get("type") == 1:
                results.append({
                    "date": date_str,
                    "measured_at": measured_at,
                    "weight_kg": round(_decode_weight(m["value"], m["unit"]), 3),
                })
    logger.info("withings_measurements_fetched", count=len(results))
    return results


def store_measurements(measurements: list[dict]) -> int:
    if not measurements:
        return 0
    with get_db() as conn:
        for m in measurements:
            conn.execute(
                "INSERT INTO body_measurements (date, source, weight_kg, measured_at) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (date, source) DO UPDATE SET weight_kg = EXCLUDED.weight_kg, measured_at = EXCLUDED.measured_at",
                (m["date"], "withings", m["weight_kg"], m.get("measured_at")),
            )
    return len(measurements)


def sync_weight(days: int = 90) -> dict:
    if not is_connected():
        return {"status": "error", "message": "Withings not connected. Please authorize in Settings."}
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    measurements = fetch_weight_measurements(start_date, end_date)
    count = store_measurements(measurements)
    try:
        for m in measurements:
            intervals_icu.update_weight(m["weight_kg"], m["date"])
    except Exception as e:
        logger.warning("withings_icu_push_failed", error=str(e))
    logger.info("withings_sync_complete", synced=count, start_date=start_date, end_date=end_date)
    return {"status": "success", "synced": count, "start_date": start_date, "end_date": end_date}


def get_status() -> dict:
    connected = is_connected()
    configured = is_configured()
    result: dict = {"connected": connected, "configured": configured}
    if connected:
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT date, weight_kg FROM body_measurements WHERE source='withings' ORDER BY date DESC LIMIT 1"
                ).fetchone()
            if row:
                result["last_measurement_date"] = row["date"]
                result["latest_weight_kg"] = row["weight_kg"]
        except Exception:
            pass
    return result


def disconnect():
    for key in ["withings_access_token", "withings_refresh_token",
                "withings_token_expiry", "withings_user_id", "withings_oauth_state"]:
        set_setting(key, "")
    logger.info("withings_disconnected")


_NOTIFY_URL = "https://wbsapi.withings.net/notify"
_APPLI_WEIGHT = 1  # Withings appli code for body measurements


def subscribe_notifications(webhook_url: str) -> bool:
    """Subscribe to Withings push notifications for weight measurements.

    Called after successful OAuth so Withings can push new measurements
    to our webhook instead of requiring manual polling.
    Returns True on success, False if subscription fails (non-fatal).
    """
    try:
        token = _get_valid_access_token()
        resp = httpx.post(
            _NOTIFY_URL,
            data={
                "action": "subscribe",
                "callbackurl": webhook_url,
                "appli": _APPLI_WEIGHT,
                "comment": "cycling-coach weight sync",
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        body = resp.json()
        if body.get("status") != 0:
            logger.warning("withings_subscribe_failed", status=body.get("status"), error=body.get("error"))
            return False
        set_setting("withings_webhook_url", webhook_url)
        logger.info("withings_subscribed", webhook_url=webhook_url)
        return True
    except Exception as e:
        logger.warning("withings_subscribe_error", error=str(e))
        return False


def unsubscribe_notifications() -> None:
    """Revoke Withings push notification subscription on disconnect."""
    webhook_url = get_setting("withings_webhook_url")
    if not webhook_url:
        return
    try:
        token = _get_valid_access_token()
        resp = httpx.post(
            _NOTIFY_URL,
            data={
                "action": "revoke",
                "callbackurl": webhook_url,
                "appli": _APPLI_WEIGHT,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        body = resp.json()
        if body.get("status") != 0:
            logger.warning("withings_unsubscribe_failed", status=body.get("status"))
    except Exception as e:
        logger.warning("withings_unsubscribe_error", error=str(e))


def handle_webhook_notification(userid: str, startdate: int, enddate: int) -> dict:
    """Handle an inbound Withings push notification.

    Withings POSTs form data with userid, appli, startdate, enddate (Unix timestamps)
    when new measurements are available. We sync only the notified window.
    """
    stored_userid = get_setting("withings_user_id")
    if stored_userid and userid != stored_userid:
        logger.warning("withings_webhook_userid_mismatch", received=userid, expected=stored_userid)
        return {"status": "ignored", "reason": "userid mismatch"}

    start_date = datetime.fromtimestamp(startdate, tz=timezone.utc).strftime("%Y-%m-%d")
    end_date = datetime.fromtimestamp(enddate, tz=timezone.utc).strftime("%Y-%m-%d")

    try:
        measurements = fetch_weight_measurements(start_date, end_date)
        count = store_measurements(measurements)
        try:
            for m in measurements:
                intervals_icu.update_weight(m["weight_kg"], m["date"])
        except Exception as e:
            logger.warning("withings_webhook_icu_push_failed", error=str(e))
        if count:
            # Recompute PMC to pick up new weight data
            from server.database import get_db
            from server.ingest import compute_daily_pmc
            with get_db() as conn:
                compute_daily_pmc(conn)
        logger.info("withings_webhook_synced", synced=count, start=start_date, end=end_date)
        return {"status": "success", "synced": count}
    except Exception as e:
        logger.error("withings_webhook_sync_failed", error=str(e))
        return {"status": "error", "message": str(e)}
