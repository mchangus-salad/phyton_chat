"""
OpenTelemetry tracing setup for CliniGraph AI.

Configures a global TracerProvider backed by one of three exporters,
controlled by the ``OTEL_EXPORTER`` environment variable:

  - ``otlp``    — Sends spans to an OTLP-HTTP collector endpoint
                  (e.g. Jaeger, Grafana Tempo, OpenTelemetry Collector).
                  Endpoint: ``OTEL_EXPORTER_OTLP_ENDPOINT`` (default: http://localhost:4318)
  - ``console`` — Pretty-prints spans to stdout (useful for local debugging).
  - ``none``    — No-op exporter; tracing infrastructure is present but silent.

Usage (called once at application startup in asgi.py / wsgi.py):

    from api.tracing import setup_tracing
    setup_tracing()

After setup, obtain a tracer anywhere in the codebase with::

    from opentelemetry import trace
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("my-operation") as span:
        span.set_attribute("key", "value")
        ...
"""
import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

logger = logging.getLogger(__name__)

_SETUP_DONE = False


def setup_tracing() -> None:
    """Initialise OpenTelemetry tracing.  Safe to call multiple times (idempotent)."""
    global _SETUP_DONE
    if _SETUP_DONE:
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "clinigraph-ai")
    exporter_type = os.getenv("OTEL_EXPORTER", "none").lower().strip()

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    if exporter_type == "otlp":
        _configure_otlp(provider)
    elif exporter_type == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        logger.info("OTel tracing: console exporter enabled")
    else:
        # Default: no-op (infrastructure present, zero overhead in prod until OTLP configured)
        logger.debug("OTel tracing: no-op exporter (set OTEL_EXPORTER=otlp|console to export)")

    trace.set_tracer_provider(provider)

    _instrument_django()

    _SETUP_DONE = True
    logger.info("OTel tracing initialised (service=%s exporter=%s)", service_name, exporter_type)


def _configure_otlp(provider: TracerProvider) -> None:
    """Attach a BatchSpanProcessor sending to an OTLP HTTP endpoint."""
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except ImportError:
        logger.warning(
            "opentelemetry-exporter-otlp-proto-http not installed; "
            "falling back to no-op exporter"
        )
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    logger.info("OTel tracing: OTLP exporter → %s", endpoint)


def _instrument_django() -> None:
    """Auto-instrument Django HTTP request/response cycle."""
    try:
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        DjangoInstrumentor().instrument()
    except Exception as exc:
        logger.warning("Failed to instrument Django with OTel: %s", exc)


def get_tracer(name: str = "clinigraph-ai"):
    """Convenience wrapper: returns a tracer using the global provider."""
    return trace.get_tracer(name)
