"""Timezone-aware date utilities for per-request and background-job contexts."""
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

# Thread-local storage for the active request's client timezone.
# Set once per chat() invocation. Background jobs (ingest, sync) leave this at UTC.
_request_tz: threading.local = threading.local()


def set_request_tz(tz: ZoneInfo) -> None:
    """Store user's ZoneInfo for the current thread (called once per request by chat())."""
    _request_tz.tz = tz


def get_request_tz() -> ZoneInfo:
    """Return the request-scoped ZoneInfo; falls back to UTC."""
    return getattr(_request_tz, "tz", ZoneInfo("UTC"))


def user_today(tz: ZoneInfo | None = None) -> str:
    """Return today's local date as YYYY-MM-DD.

    If tz is None, reads from thread-local (set by set_request_tz).
    Pass tz explicitly in non-agent contexts (routers, background jobs).
    """
    if tz is None:
        tz = get_request_tz()
    return datetime.now(tz).strftime("%Y-%m-%d")
