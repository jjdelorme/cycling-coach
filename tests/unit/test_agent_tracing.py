"""Unit tests for OTel span instrumentation in server/coaching/agent.py."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["TESTING"] = "true"


@pytest.fixture(autouse=True)
def configure_telemetry_for_tests():
    """Ensure telemetry is configured with InMemorySpanExporter for each test.

    We reload server.telemetry to get fresh module state, then also reload
    server.coaching.agent so its module-level _tracer is re-created from
    the new TracerProvider. Without the agent reload, _tracer would remain
    bound to the previous provider's span processor.
    """
    import importlib
    import server.telemetry as tel
    importlib.reload(tel)
    tel.configure_telemetry()
    tel.get_test_exporter().clear()

    # Reload agent so _tracer = get_tracer(__name__) re-runs against the new provider
    import server.coaching.agent  # noqa: F401 — ensure it's in sys.modules first
    importlib.reload(server.coaching.agent)

    yield
    tel.get_test_exporter().clear()


def _make_text_event(text: str, author: str = "cycling_coach"):
    """Build a minimal ADK event with a text part."""
    part = MagicMock()
    part.text = text
    part.function_call = None
    part.function_response = None

    content = MagicMock()
    content.parts = [part]

    event = MagicMock()
    event.content = content
    event.author = author
    return event


def _make_tool_call_event(fn_name: str):
    """Build a minimal ADK event that represents a tool call."""
    fc = MagicMock()
    fc.name = fn_name

    part = MagicMock()
    part.text = None
    part.function_call = fc
    part.function_response = None

    content = MagicMock()
    content.parts = [part]

    event = MagicMock()
    event.content = content
    event.author = "cycling_coach"
    return event


@pytest.mark.asyncio
async def test_chat_produces_agent_chat_span():
    """chat() wraps runner.run_async() in an agent.chat OTel span."""
    from server.telemetry import get_test_exporter

    text_event = _make_text_event("Hello, athlete!")
    mock_runner = AsyncMock()
    mock_runner.run_async = MagicMock(return_value=_async_gen([text_event]))

    mock_session = MagicMock()
    mock_session.get_session = AsyncMock(return_value=MagicMock())
    mock_session.create_session = AsyncMock(return_value=MagicMock())
    mock_session.add_session_to_memory = AsyncMock()

    with patch("server.coaching.agent.get_runner", return_value=(mock_runner, mock_session, mock_session)), \
         patch("server.coaching.agent.get_setting", return_value=None):
        from server.coaching import agent as agent_mod
        await agent_mod.chat(
            message="How am I doing?",
            user_id="test_user",
            session_id="test_session",
        )

    exporter = get_test_exporter()
    finished = exporter.get_finished_spans()
    span_names = [s.name for s in finished]
    assert "agent.chat" in span_names, f"agent.chat span missing from: {span_names}"


@pytest.mark.asyncio
async def test_chat_span_has_session_and_user_attributes():
    """agent.chat span carries session_id and user_id attributes."""
    from server.telemetry import get_test_exporter

    text_event = _make_text_event("Good job!")
    mock_runner = AsyncMock()
    mock_runner.run_async = MagicMock(return_value=_async_gen([text_event]))

    mock_session_svc = MagicMock()
    mock_session_svc.get_session = AsyncMock(return_value=MagicMock())
    mock_session_svc.create_session = AsyncMock(return_value=MagicMock())
    mock_memory_svc = MagicMock()
    mock_memory_svc.add_session_to_memory = AsyncMock()

    with patch("server.coaching.agent.get_runner",
               return_value=(mock_runner, mock_session_svc, mock_memory_svc)), \
         patch("server.coaching.agent.get_setting", return_value=None):
        from server.coaching import agent as agent_mod
        await agent_mod.chat(
            message="What's my CTL?",
            user_id="athlete_42",
            session_id="sess_abc",
        )

    exporter = get_test_exporter()
    chat_spans = [s for s in exporter.get_finished_spans() if s.name == "agent.chat"]
    assert chat_spans, "agent.chat span not found"

    attrs = chat_spans[0].attributes
    assert attrs.get("session_id") == "sess_abc"
    assert attrs.get("user_id") == "athlete_42"


@pytest.mark.asyncio
async def test_tool_call_produces_child_span():
    """Each function_call event produces an agent.tool_call child span."""
    from server.telemetry import get_test_exporter

    tool_event = _make_tool_call_event("get_pmc_metrics")
    text_event = _make_text_event("Your CTL is 72.")
    mock_runner = AsyncMock()
    mock_runner.run_async = MagicMock(return_value=_async_gen([tool_event, text_event]))

    mock_session_svc = MagicMock()
    mock_session_svc.get_session = AsyncMock(return_value=MagicMock())
    mock_session_svc.create_session = AsyncMock(return_value=MagicMock())
    mock_memory_svc = MagicMock()
    mock_memory_svc.add_session_to_memory = AsyncMock()

    with patch("server.coaching.agent.get_runner",
               return_value=(mock_runner, mock_session_svc, mock_memory_svc)), \
         patch("server.coaching.agent.get_setting", return_value=None):
        from server.coaching import agent as agent_mod
        await agent_mod.chat(
            message="What's my fitness?",
            user_id="athlete_42",
            session_id="sess_abc",
        )

    exporter = get_test_exporter()
    finished = exporter.get_finished_spans()
    tool_spans = [s for s in finished if s.name == "agent.tool_call"]
    assert tool_spans, f"agent.tool_call span missing from: {[s.name for s in finished]}"

    tool_span = tool_spans[0]
    assert tool_span.attributes.get("tool_name") == "get_pmc_metrics"


@pytest.mark.asyncio
async def test_tool_call_span_is_child_of_chat_span():
    """agent.tool_call span must be a child of agent.chat span."""
    from server.telemetry import get_test_exporter

    tool_event = _make_tool_call_event("get_recent_rides")
    text_event = _make_text_event("Here are your recent rides.")
    mock_runner = AsyncMock()
    mock_runner.run_async = MagicMock(return_value=_async_gen([tool_event, text_event]))

    mock_session_svc = MagicMock()
    mock_session_svc.get_session = AsyncMock(return_value=MagicMock())
    mock_session_svc.create_session = AsyncMock(return_value=MagicMock())
    mock_memory_svc = MagicMock()
    mock_memory_svc.add_session_to_memory = AsyncMock()

    with patch("server.coaching.agent.get_runner",
               return_value=(mock_runner, mock_session_svc, mock_memory_svc)), \
         patch("server.coaching.agent.get_setting", return_value=None):
        from server.coaching import agent as agent_mod
        await agent_mod.chat(
            message="Show my rides",
            user_id="u1",
            session_id="s1",
        )

    exporter = get_test_exporter()
    finished = exporter.get_finished_spans()
    chat_span = next((s for s in finished if s.name == "agent.chat"), None)
    tool_span = next((s for s in finished if s.name == "agent.tool_call"), None)

    assert chat_span is not None
    assert tool_span is not None

    # Tool span's parent span ID must match chat span's span ID
    assert tool_span.parent.span_id == chat_span.get_span_context().span_id


async def _async_gen(items):
    """Helper: turn a list into an async generator for mocking run_async."""
    for item in items:
        yield item
