"""Unit tests verifying timezone dependency is wired into all ride-querying router endpoints.

These tests verify function signatures and dependency injection, not SQL execution.
They catch the bug where an endpoint hardcodes 'UTC' or omits the tz parameter entirely.
"""

import inspect
from zoneinfo import ZoneInfo


def test_route_matches_accepts_tz_dependency():
    """route_matches must accept a tz parameter from get_client_tz, not hardcode UTC."""
    from server.routers.analysis import route_matches
    sig = inspect.signature(route_matches)
    assert "tz" in sig.parameters, (
        "route_matches is missing a 'tz' parameter -- it must use get_client_tz"
    )
    param = sig.parameters["tz"]
    assert param.annotation is ZoneInfo, (
        f"route_matches 'tz' parameter should be ZoneInfo, got {param.annotation}"
    )


def test_get_week_plans_batch_accepts_tz_dependency():
    """get_week_plans_batch must accept a tz parameter from get_client_tz."""
    from server.routers.planning import get_week_plans_batch
    sig = inspect.signature(get_week_plans_batch)
    assert "tz" in sig.parameters, (
        "get_week_plans_batch is missing a 'tz' parameter -- it must use get_client_tz"
    )
    param = sig.parameters["tz"]
    assert param.annotation is ZoneInfo, (
        f"get_week_plans_batch 'tz' parameter should be ZoneInfo, got {param.annotation}"
    )


def test_all_ride_querying_analysis_endpoints_have_tz():
    """All analysis endpoints that query rides must have a tz parameter."""
    from server.routers.analysis import zone_distribution, efficiency_factor, route_matches
    for fn in [zone_distribution, efficiency_factor, route_matches]:
        sig = inspect.signature(fn)
        assert "tz" in sig.parameters, (
            f"{fn.__name__} is missing a 'tz' parameter"
        )


def test_all_ride_querying_rides_endpoints_have_tz():
    """All rides endpoints that query rides.date must have a tz parameter."""
    from server.routers.rides import list_rides, daily_summary, weekly_summary, monthly_summary, delete_ride
    for fn in [list_rides, daily_summary, weekly_summary, monthly_summary, delete_ride]:
        sig = inspect.signature(fn)
        assert "tz" in sig.parameters, (
            f"{fn.__name__} is missing a 'tz' parameter"
        )


def test_all_ride_querying_planning_endpoints_have_tz():
    """All planning endpoints that query rides must have a tz parameter."""
    from server.routers.planning import (
        get_activity_dates, weekly_overview, plan_compliance,
        get_week_plan, get_week_plans_batch,
    )
    for fn in [get_activity_dates, weekly_overview, plan_compliance, get_week_plan, get_week_plans_batch]:
        sig = inspect.signature(fn)
        assert "tz" in sig.parameters, (
            f"{fn.__name__} is missing a 'tz' parameter"
        )
