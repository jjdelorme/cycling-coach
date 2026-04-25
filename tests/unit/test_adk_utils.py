"""Tests for the json_safe_tool wrapper."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from server.utils.adk import json_safe_tool


def test_wraps_date_to_iso_string():
    @json_safe_tool
    def tool():
        return {"d": date(2026, 4, 23)}

    result = tool()
    assert result == {"d": "2026-04-23"}


def test_wraps_datetime_to_iso_string():
    @json_safe_tool
    def tool():
        return {"ts": datetime(2026, 4, 23, 12, 30, 0, tzinfo=timezone.utc)}

    result = tool()
    assert isinstance(result["ts"], str)
    assert result["ts"].startswith("2026-04-23T12:30:00")


def test_wraps_uuid_to_string():
    uid = UUID("12345678-1234-5678-1234-567812345678")

    @json_safe_tool
    def tool():
        return {"id": uid}

    result = tool()
    assert result == {"id": "12345678-1234-5678-1234-567812345678"}


def test_wraps_nested_structures():
    @json_safe_tool
    def tool():
        return {
            "rides": [
                {"date": date(2026, 4, 1), "id": UUID(int=1)},
                {"date": date(2026, 4, 2), "id": UUID(int=2)},
            ],
            "meta": {"generated": datetime(2026, 4, 23, tzinfo=timezone.utc)},
        }

    result = tool()
    assert result["rides"][0]["date"] == "2026-04-01"
    assert result["rides"][1]["date"] == "2026-04-02"
    assert isinstance(result["rides"][0]["id"], str)
    assert isinstance(result["meta"]["generated"], str)


def test_passes_through_primitives():
    @json_safe_tool
    def tool():
        return {"n": 42, "s": "hello", "b": True, "none": None, "f": 1.5}

    assert tool() == {"n": 42, "s": "hello", "b": True, "none": None, "f": 1.5}


def test_handles_decimal():
    @json_safe_tool
    def tool():
        return {"amount": Decimal("12.34")}

    result = tool()
    assert result["amount"] == "12.34" or result["amount"] == 12.34


def test_preserves_function_metadata():
    @json_safe_tool
    def get_recent_rides(athlete_id: str, days: int = 7) -> dict:
        """Return recent rides for the athlete."""
        return {}

    assert get_recent_rides.__name__ == "get_recent_rides"
    assert get_recent_rides.__doc__ == "Return recent rides for the athlete."
    assert get_recent_rides.__annotations__ == {
        "athlete_id": str,
        "days": int,
        "return": dict,
    }


def test_passes_arguments_through():
    @json_safe_tool
    def tool(a, b, c=None):
        return {"a": a, "b": b, "c": c}

    assert tool(1, 2, c=3) == {"a": 1, "b": 2, "c": 3}


def test_rejects_adk_tool_objects():
    """Regression: PreloadMemoryTool / AgentTool / GoogleSearchTool are
    BaseTool instances (not functions). Wrapping them would crash later
    in ADK schema generation. Fail fast at registration instead."""

    class FakeAdkTool:
        def _get_declaration(self):
            return {}

    with pytest.raises(TypeError, match="ADK tool object"):
        json_safe_tool(FakeAdkTool())


def test_rejects_non_function_callables():
    """Plain class instances with __call__ are not regular functions and
    should also be rejected — ADK expects either a tool object (handled
    above) or a real function with introspectable signature."""

    class CallableInstance:
        def __call__(self, x):
            return x

    with pytest.raises(TypeError, match="expected a function"):
        json_safe_tool(CallableInstance())
