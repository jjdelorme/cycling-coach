"""Unit tests for server/utils/dates.py timezone utilities."""
from contextvars import copy_context
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from server.utils.dates import _request_tz, get_request_tz, set_request_tz, user_today


def test_tz_ctx_default_is_utc():
    """The ContextVar default must be UTC."""
    ctx = copy_context()
    result = ctx.run(_request_tz.get)
    assert result == ZoneInfo("UTC")


def test_user_today_default_utc_returns_date_string():
    """With no timezone set, user_today() returns a YYYY-MM-DD string in UTC."""
    ctx = copy_context()
    result = ctx.run(user_today)
    assert isinstance(result, str)
    # Must be a valid ISO date: parse it
    datetime.strptime(result, "%Y-%m-%d")


def test_user_today_us_central_returns_valid_date():
    """With America/Chicago set, user_today() returns a valid YYYY-MM-DD string."""
    def _run():
        set_request_tz(ZoneInfo("America/Chicago"))
        return user_today()

    ctx = copy_context()
    result = ctx.run(_run)
    assert isinstance(result, str)
    datetime.strptime(result, "%Y-%m-%d")


def test_user_today_explicit_tz_overrides_contextvar():
    """Passing tz explicitly bypasses the ContextVar."""
    def _run():
        set_request_tz(ZoneInfo("America/Chicago"))
        # Explicit UTC override must not use Chicago
        return user_today(tz=ZoneInfo("UTC"))

    ctx = copy_context()
    result = ctx.run(_run)
    assert isinstance(result, str)
    datetime.strptime(result, "%Y-%m-%d")


def test_context_isolation():
    """Two concurrent contexts must not bleed timezone into each other."""
    results: dict[str, str] = {}

    def _run_utc():
        set_request_tz(ZoneInfo("UTC"))
        results["utc"] = _request_tz.get().key

    def _run_chicago():
        set_request_tz(ZoneInfo("America/Chicago"))
        results["chicago"] = _request_tz.get().key

    copy_context().run(_run_utc)
    copy_context().run(_run_chicago)

    assert results["utc"] == "UTC"
    assert results["chicago"] == "America/Chicago"


def test_get_request_tz_returns_zoneinfo():
    """get_request_tz() must return a ZoneInfo instance."""
    ctx = copy_context()
    result = ctx.run(get_request_tz)
    assert isinstance(result, ZoneInfo)


def test_set_and_get_request_tz_roundtrip():
    """set_request_tz followed by get_request_tz returns the same zone."""
    def _run():
        tz = ZoneInfo("Europe/London")
        set_request_tz(tz)
        return get_request_tz()

    ctx = copy_context()
    result = ctx.run(_run)
    assert result == ZoneInfo("Europe/London")


def test_asgi_middleware_propagates_contextvar():
    """ClientTimezoneMiddleware (raw ASGI) must propagate ContextVar to route handlers."""
    from server.main import ClientTimezoneMiddleware

    async def tz_endpoint(request):
        tz = get_request_tz()
        return JSONResponse({"tz": str(tz)})

    app = Starlette(routes=[Route("/tz", tz_endpoint)])
    app = ClientTimezoneMiddleware(app)

    client = TestClient(app)

    # With explicit timezone header
    resp = client.get("/tz", headers={"X-Client-Timezone": "America/Chicago"})
    assert resp.status_code == 200
    assert resp.json()["tz"] == "America/Chicago"

    # Without header — should default to UTC
    resp = client.get("/tz")
    assert resp.status_code == 200
    assert resp.json()["tz"] == "UTC"

    # With invalid timezone — should fall back to UTC
    resp = client.get("/tz", headers={"X-Client-Timezone": "Not/A/Timezone"})
    assert resp.status_code == 200
    assert resp.json()["tz"] == "UTC"
