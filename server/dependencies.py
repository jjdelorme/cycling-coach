"""FastAPI shared dependencies."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import Request


def get_client_tz(request: Request) -> ZoneInfo:
    """Return the user's local ZoneInfo, populated by ClientTimezoneMiddleware.
    Falls back to UTC if middleware did not set it.
    """
    tz_name = getattr(request.state, "client_tz_str", "UTC")
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        return ZoneInfo("UTC")
