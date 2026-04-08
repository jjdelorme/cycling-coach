"""OpenTelemetry tracing configuration.

Usage:
    from server.telemetry import configure_telemetry, get_tracer

    configure_telemetry()                # call once at startup
    tracer = get_tracer(__name__)        # module-level tracer
    with tracer.start_as_current_span("my.operation") as span:
        span.set_attribute("key", "value")
        ...

In tests (TESTING=true), uses InMemorySpanExporter so no GCP calls are made.
Retrieve captured spans via get_test_exporter().get_finished_spans().
"""

import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

try:
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
except ImportError:
    CloudTraceSpanExporter = None  # type: ignore[assignment,misc]

try:
    from opentelemetry.propagator.cloud_trace_propagator import CloudTraceFormatPropagator
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.propagators.b3 import B3Format
except ImportError:
    CloudTraceFormatPropagator = None  # type: ignore[assignment]
    CompositePropagator = None         # type: ignore[assignment]
    B3Format = None                    # type: ignore[assignment]

# Module-level state
_provider: Optional[TracerProvider] = None
_test_exporter: Optional[InMemorySpanExporter] = None


def configure_telemetry() -> None:
    """Set up TracerProvider with the appropriate exporter.

    - TESTING=true  → InMemorySpanExporter with SimpleSpanProcessor (synchronous;
                       use get_test_exporter() to inspect captured spans)
    - otherwise     → CloudTraceSpanExporter via BatchSpanProcessor
    """
    global _provider, _test_exporter

    _provider = TracerProvider()

    if os.environ.get("TESTING", "").lower() == "true":
        _test_exporter = InMemorySpanExporter()
        # SimpleSpanProcessor exports synchronously so spans are immediately
        # visible in get_finished_spans() — essential for test assertions.
        _provider.add_span_processor(SimpleSpanProcessor(_test_exporter))
    else:
        if CloudTraceSpanExporter is None:
            raise ImportError(
                "opentelemetry-exporter-gcp-trace is required in non-test environments. "
                "Install it via: pip install opentelemetry-exporter-gcp-trace"
            )
        gcp_exporter = CloudTraceSpanExporter()
        _provider.add_span_processor(BatchSpanProcessor(gcp_exporter))

    # OTel's set_tracer_provider() is guarded by a Once lock that prevents
    # overriding after the first call. Reset the lock so this function can be
    # called multiple times (e.g., module reload in unit tests).
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER = None                  # type: ignore[attr-defined]
    trace.set_tracer_provider(_provider)


def get_tracer(name: str) -> trace.Tracer:
    """Return a tracer for the given instrumentation scope name."""
    return trace.get_tracer(name)


def get_test_exporter() -> Optional[InMemorySpanExporter]:
    """Return the InMemorySpanExporter used in test environments.

    Returns None if configure_telemetry() has not been called or if running
    in a non-test environment.
    """
    return _test_exporter


def shutdown() -> None:
    """Flush and shut down the TracerProvider. Call during application shutdown."""
    if _provider is not None:
        _provider.shutdown()
