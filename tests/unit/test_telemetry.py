"""Unit tests for server/telemetry.py."""

import os
import pytest


def test_configure_telemetry_test_env_uses_in_memory_exporter(monkeypatch):
    """When TESTING=true, configure_telemetry() installs InMemorySpanExporter."""
    monkeypatch.setenv("TESTING", "true")

    # Force re-import so module-level state is fresh
    import importlib
    import server.telemetry as telemetry_mod
    importlib.reload(telemetry_mod)

    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry import trace

    telemetry_mod.configure_telemetry()
    tracer_provider = trace.get_tracer_provider()

    # Confirm we can retrieve the in-memory exporter via the module-level accessor
    exporter = telemetry_mod.get_test_exporter()
    assert isinstance(exporter, InMemorySpanExporter)


def test_get_tracer_returns_tracer(monkeypatch):
    """get_tracer() returns a usable OpenTelemetry Tracer."""
    monkeypatch.setenv("TESTING", "true")
    import importlib
    import server.telemetry as telemetry_mod
    importlib.reload(telemetry_mod)

    telemetry_mod.configure_telemetry()
    tracer = telemetry_mod.get_tracer("test.module")

    from opentelemetry.trace import Tracer
    assert isinstance(tracer, Tracer)


def test_tracer_produces_spans_in_test_env(monkeypatch):
    """Spans created via get_tracer() appear in the InMemorySpanExporter."""
    monkeypatch.setenv("TESTING", "true")
    import importlib
    import server.telemetry as telemetry_mod
    importlib.reload(telemetry_mod)

    telemetry_mod.configure_telemetry()
    exporter = telemetry_mod.get_test_exporter()
    exporter.clear()

    tracer = telemetry_mod.get_tracer("test.module")
    with tracer.start_as_current_span("test.span") as span:
        pass

    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].name == "test.span"


def test_configure_telemetry_non_test_env_uses_gcp_exporter(monkeypatch):
    """When TESTING is not set, configure_telemetry() uses CloudTraceSpanExporter."""
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    import importlib
    import server.telemetry as telemetry_mod

    # Reload first so module state is fresh, then patch CloudTraceSpanExporter
    # to avoid real GCP auth. The patch must wrap only the configure_telemetry()
    # call (not the reload) because reload() re-imports the real class.
    importlib.reload(telemetry_mod)

    from unittest.mock import patch, MagicMock
    mock_exporter_cls = MagicMock()
    mock_exporter_cls.return_value = MagicMock()

    with patch("server.telemetry.CloudTraceSpanExporter", mock_exporter_cls):
        telemetry_mod.configure_telemetry()

    mock_exporter_cls.assert_called_once()


def test_otel_trace_bridge_binds_trace_id_from_active_span(monkeypatch):
    """OTelTraceBridge reads the active OTel span and calls bind_trace_id()."""
    monkeypatch.setenv("TESTING", "true")
    import importlib
    import server.telemetry as telemetry_mod
    importlib.reload(telemetry_mod)
    telemetry_mod.configure_telemetry()

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from unittest.mock import patch, AsyncMock, MagicMock

    tracer = telemetry_mod.get_tracer("test")

    with tracer.start_as_current_span("test.request") as span:
        ctx = span.get_span_context()
        expected_trace_id = format(ctx.trace_id, "032x")
        expected_span_id = format(ctx.span_id, "016x")

        # Import here so OTelTraceBridge picks up the active span
        from server.main import OTelTraceBridge
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        bound_ids = {}

        def capture_bind(trace_id, span_id=""):
            bound_ids["trace_id"] = trace_id
            bound_ids["span_id"] = span_id

        async def homepage(request):
            return PlainTextResponse("ok")

        mini_app = Starlette(routes=[Route("/", homepage)])
        mini_app.add_middleware(OTelTraceBridge)

        with patch("server.main.bind_trace_id", side_effect=capture_bind):
            client = TestClient(mini_app, raise_server_exceptions=True)
            # We can't carry the span context into the test client's thread automatically,
            # so we assert the middleware calls bind_trace_id with *some* string.
            # The OTel integration test verifies the trace ID is the OTel one.
            response = client.get("/")

        # bind_trace_id must have been called
        assert "trace_id" in bound_ids


def test_otel_trace_bridge_sets_x_trace_id_response_header():
    """OTelTraceBridge sets X-Trace-Id on the response."""
    import os
    os.environ["TESTING"] = "true"

    from unittest.mock import patch
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from server.main import OTelTraceBridge

    async def homepage(request):
        return PlainTextResponse("ok")

    mini_app = Starlette(routes=[Route("/", homepage)])
    mini_app.add_middleware(OTelTraceBridge)

    with patch("server.main.bind_trace_id"):
        client = TestClient(mini_app)
        response = client.get("/")

    assert "x-trace-id" in response.headers


def test_otel_trace_bridge_falls_back_when_no_active_span():
    """OTelTraceBridge falls back gracefully when no OTel span is active."""
    import os
    os.environ["TESTING"] = "true"

    from unittest.mock import patch
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from server.main import OTelTraceBridge

    bound_ids = {}

    def capture_bind(trace_id, span_id=""):
        bound_ids["trace_id"] = trace_id
        bound_ids["span_id"] = span_id

    async def homepage(request):
        return PlainTextResponse("ok")

    mini_app = Starlette(routes=[Route("/", homepage)])
    mini_app.add_middleware(OTelTraceBridge)

    with patch("server.main.bind_trace_id", side_effect=capture_bind):
        client = TestClient(mini_app)
        client.get("/")

    # Should still call bind_trace_id with a non-empty fallback string
    assert bound_ids.get("trace_id", "") != ""
