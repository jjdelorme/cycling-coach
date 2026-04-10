"""Integration tests for OpenTelemetry tracing."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clear_spans():
    """Clear the in-memory exporter before each test."""
    from server.telemetry import get_test_exporter
    exporter = get_test_exporter()
    if exporter:
        exporter.clear()
    yield


def test_http_request_produces_otel_span(client: TestClient):
    """A GET /api/health should produce at least one finished OTel span."""
    from server.telemetry import get_test_exporter

    response = client.get("/api/health")
    assert response.status_code == 200

    exporter = get_test_exporter()
    assert exporter is not None, "InMemorySpanExporter must be configured (TESTING=true)"

    finished = exporter.get_finished_spans()
    assert len(finished) >= 1

    span_names = [s.name for s in finished]
    # FastAPIInstrumentor names spans after the route pattern
    assert any("health" in name or "GET" in name for name in span_names), (
        f"Expected a health-related span, got: {span_names}"
    )


def test_x_trace_id_header_matches_otel_trace_id(client: TestClient):
    """X-Trace-Id response header must equal the OTel trace ID (hex)."""
    from server.telemetry import get_test_exporter

    response = client.get("/api/health")
    assert response.status_code == 200

    x_trace_id = response.headers.get("x-trace-id", "")
    assert x_trace_id != "", "X-Trace-Id header must be present"

    exporter = get_test_exporter()
    finished = exporter.get_finished_spans()
    assert finished, "At least one span must be produced"

    otel_trace_ids = {format(s.get_span_context().trace_id, "032x") for s in finished}
    assert x_trace_id in otel_trace_ids, (
        f"X-Trace-Id '{x_trace_id}' not found in OTel trace IDs {otel_trace_ids}"
    )


def test_get_trace_id_returns_otel_trace_id_during_request():
    """get_trace_id() must return the OTel trace ID while processing a request."""
    import os
    os.environ["TESTING"] = "true"

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from server.main import OTelTraceBridge
    from server.logging_config import get_trace_id
    from server.telemetry import get_test_exporter

    captured = {}

    # Use a standalone minimal app so the SPA catch-all in server.main (only
    # present when frontend/dist exists) cannot shadow our probe route.
    probe_app = FastAPI()
    probe_app.add_middleware(OTelTraceBridge)
    FastAPIInstrumentor.instrument_app(probe_app)

    @probe_app.get("/probe")
    def _probe():
        captured["trace_id"] = get_trace_id()
        return {"ok": True}

    client = TestClient(probe_app)
    get_test_exporter().clear()

    client.get("/probe")

    finished = get_test_exporter().get_finished_spans()
    otel_trace_ids = {format(s.get_span_context().trace_id, "032x") for s in finished}

    assert captured.get("trace_id", "") in otel_trace_ids, (
        f"get_trace_id() returned '{captured.get('trace_id')}' "
        f"but OTel trace IDs are {otel_trace_ids}"
    )


def test_coaching_chat_produces_agent_chat_span():
    """POST /api/coaching/chat produces an agent.chat OTel span."""
    import os
    os.environ["TESTING"] = "true"

    from fastapi.testclient import TestClient
    from server.main import app
    from server.telemetry import get_test_exporter
    from unittest.mock import patch, AsyncMock

    get_test_exporter().clear()

    # Mock the agent's chat() so no real ADK/Gemini call is made,
    # but the span instrumentation in chat() still executes.
    # We need to call the REAL chat() function but mock runner.run_async.
    async def mock_run_async(**kwargs):
        # Yield one minimal text event
        part = type("Part", (), {"text": "Hello!", "function_call": None, "function_response": None})()
        content = type("Content", (), {"parts": [part]})()
        event = type("Event", (), {"content": content, "author": "cycling_coach"})()
        yield event

    mock_runner = type("Runner", (), {"run_async": lambda self, **kw: mock_run_async(**kw)})()
    mock_session_svc = AsyncMock()
    mock_session_svc.get_session = AsyncMock(return_value=AsyncMock())
    mock_session_svc.create_session = AsyncMock(return_value=AsyncMock())
    mock_memory_svc = AsyncMock()
    mock_memory_svc.add_session_to_memory = AsyncMock()

    with patch("server.coaching.agent.get_runner",
               return_value=(mock_runner, mock_session_svc, mock_memory_svc)), \
         patch("server.coaching.agent.get_setting", return_value=None):

        client = TestClient(app)
        response = client.post(
            "/api/coaching/chat",
            json={"message": "How am I doing?", "session_id": "integration-test-session"},
        )

    assert response.status_code == 200

    exporter = get_test_exporter()
    finished = exporter.get_finished_spans()
    span_names = [s.name for s in finished]
    assert "agent.chat" in span_names, (
        f"agent.chat span not found in finished spans: {span_names}"
    )


def test_coaching_chat_span_attributes():
    """agent.chat span carries session_id attribute matching the request."""
    import os
    os.environ["TESTING"] = "true"

    from fastapi.testclient import TestClient
    from server.main import app
    from server.telemetry import get_test_exporter
    from unittest.mock import patch, AsyncMock

    get_test_exporter().clear()

    async def mock_run_async(**kwargs):
        part = type("Part", (), {"text": "Roger!", "function_call": None, "function_response": None})()
        content = type("Content", (), {"parts": [part]})()
        event = type("Event", (), {"content": content, "author": "cycling_coach"})()
        yield event

    mock_runner = type("Runner", (), {"run_async": lambda self, **kw: mock_run_async(**kw)})()
    mock_session_svc = AsyncMock()
    mock_session_svc.get_session = AsyncMock(return_value=AsyncMock())
    mock_session_svc.create_session = AsyncMock(return_value=AsyncMock())
    mock_memory_svc = AsyncMock()
    mock_memory_svc.add_session_to_memory = AsyncMock()

    session_id = "e2e-span-attrs-test"

    with patch("server.coaching.agent.get_runner",
               return_value=(mock_runner, mock_session_svc, mock_memory_svc)), \
         patch("server.coaching.agent.get_setting", return_value=None):

        client = TestClient(app)
        client.post(
            "/api/coaching/chat",
            json={"message": "Plan my week.", "session_id": session_id},
        )

    exporter = get_test_exporter()
    chat_spans = [s for s in exporter.get_finished_spans() if s.name == "agent.chat"]
    assert chat_spans, "agent.chat span not found"

    attrs = chat_spans[0].attributes
    assert attrs.get("session_id") == session_id
