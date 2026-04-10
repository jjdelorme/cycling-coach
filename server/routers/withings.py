"""Withings integration endpoints."""
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from server.auth import CurrentUser, require_read, require_write
from server.logging_config import get_logger
from server.services import withings as svc

logger = get_logger(__name__)
router = APIRouter(prefix="/api/withings", tags=["withings"])


def _webhook_url_from_request(request: Request) -> str:
    """Derive the public webhook URL from the incoming request base URL."""
    from server.config import WITHINGS_REDIRECT_URI
    # In production the redirect URI is the public Cloud Run URL; swap /callback → /webhook.
    # In local dev this won't be reachable by Withings, but we still register it so
    # the subscription is in place when deployed.
    return WITHINGS_REDIRECT_URI.replace("/callback", "/webhook")


@router.get("/status")
async def status(user: CurrentUser = Depends(require_read)):
    return svc.get_status()


@router.get("/auth-url")
async def auth_url(user: CurrentUser = Depends(require_write)):
    if not svc.is_configured():
        raise HTTPException(
            status_code=400,
            detail="Withings not configured. Set WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET.",
        )
    from server.config import WITHINGS_REDIRECT_URI
    url = svc.get_auth_url(WITHINGS_REDIRECT_URI)
    return {"url": url}


@router.get("/callback")
async def callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
):
    if error:
        logger.warning("withings_oauth_error", error=error)
        return HTMLResponse(
            '<meta http-equiv="refresh" content="0;url=/settings?withings=error">'
        )
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    from server.config import WITHINGS_REDIRECT_URI
    result = svc.exchange_code(code, state, WITHINGS_REDIRECT_URI)
    if result["status"] == "error":
        logger.error("withings_exchange_failed", message=result.get("message"))
        return HTMLResponse(
            '<meta http-equiv="refresh" content="0;url=/settings?withings=error">'
        )

    # Subscribe to push notifications so Withings calls us when new data arrives.
    webhook_url = _webhook_url_from_request(request)
    svc.subscribe_notifications(webhook_url)

    return HTMLResponse(
        '<meta http-equiv="refresh" content="0;url=/settings?withings=connected">'
    )


@router.post("/webhook")
async def webhook(
    userid: str = Form(...),
    appli: int = Form(...),
    startdate: int = Form(...),
    enddate: int = Form(...),
    date: str = Form(None),
):
    """Inbound Withings push notification.

    Withings POSTs form data here when new measurements are available.
    We only act on appli=1 (body measurements / weight).
    Must return HTTP 200 quickly — do not block on slow operations.
    """
    logger.info("withings_webhook_received", userid=userid, appli=appli,
                startdate=startdate, enddate=enddate)

    if appli != 1:
        # Not a weight measurement notification — ignore
        return {"status": "ignored", "appli": appli}

    result = svc.handle_webhook_notification(userid, startdate, enddate)
    return result


@router.post("/sync")
async def sync(
    days: int = Query(90, ge=1, le=365),
    user: CurrentUser = Depends(require_write),
):
    if not svc.is_connected():
        raise HTTPException(
            status_code=400,
            detail="Withings not connected. Authorize first via /api/withings/auth-url.",
        )
    result = svc.sync_weight(days=days)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    # Trigger PMC recompute after syncing weight data
    try:
        from server.database import get_db
        from server.ingest import compute_daily_pmc
        with get_db() as conn:
            compute_daily_pmc(conn)
    except Exception as e:
        logger.warning("withings_pmc_recompute_failed", error=str(e))
    return result


@router.delete("/disconnect")
async def disconnect(user: CurrentUser = Depends(require_write)):
    svc.unsubscribe_notifications()
    svc.disconnect()
    return {"status": "disconnected"}
