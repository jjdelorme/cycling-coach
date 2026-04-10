"""Timezone-aware date utilities for per-request and background-job contexts.

Uses ContextVar (not threading.local) so concurrent async requests each carry
their own timezone without cross-contamination.
"""
from contextvars import ContextVar
from datetime import datetime
from zoneinfo import ZoneInfo

# Per-request timezone context.
# Set by ClientTimezoneMiddleware on every HTTP request.
# Background jobs (ingest, sync) leave this at the default (UTC).
_request_tz: ContextVar[ZoneInfo] = ContextVar("request_tz", default=ZoneInfo("UTC"))


def set_request_tz(tz: ZoneInfo) -> None:
    """Store user's ZoneInfo for the current async task context.

    Called by ClientTimezoneMiddleware on every HTTP request, and explicitly
    by the coaching chat() function when tz is known.
    """
    _request_tz.set(tz)


def get_request_tz() -> ZoneInfo:
    """Return the request-scoped ZoneInfo; falls back to UTC."""
    return _request_tz.get()


def user_today(tz: ZoneInfo | None = None) -> str:
    """Return today's local date as YYYY-MM-DD.

    If tz is None, reads from the ContextVar (set by set_request_tz).
    Pass tz explicitly in non-request contexts (background jobs, tests).
    """
    if tz is None:
        tz = _request_tz.get()
    return datetime.now(tz).strftime("%Y-%m-%d")
