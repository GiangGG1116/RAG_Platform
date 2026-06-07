"""
Observability setup: OpenTelemetry tracing, Prometheus metrics, structured logging.

Call `setup_observability(service_name)` during app startup to configure
tracing, metrics, and structured logging for any microservice.
"""
import logging
import re
import sys
from typing import Any

import structlog
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from shared.config import get_settings


def setup_tracing(service_name: str) -> TracerProvider:
    """Configure OpenTelemetry tracing with OTLP exporter."""
    settings = get_settings()
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": "production",
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    return provider


def setup_metrics(service_name: str) -> MeterProvider:
    """Configure OpenTelemetry metrics with OTLP exporter."""
    settings = get_settings()
    resource = Resource.create({
        "service.name": service_name,
    })

    exporter = OTLPMetricExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=30000)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    return provider


# ── PII Masking ──────────────────────────────────────────
_PII_PATTERNS = [
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[EMAIL_REDACTED]"),
    (re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"), "[PHONE_REDACTED]"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[API_KEY_REDACTED]"),
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[IP_REDACTED]"),
]


def _mask_pii_processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Mask PII (emails, phones, API keys, IPs) in log events."""
    event = event_dict.get("event", "")
    if isinstance(event, str):
        for pattern, replacement in _PII_PATTERNS:
            event = pattern.sub(replacement, event)
        event_dict["event"] = event
    return event_dict


def setup_logging(service_name: str) -> None:
    """Configure structured logging with structlog."""
    settings = get_settings()

    # Shared processors
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        _mask_pii_processor,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
    ]

    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()  # type: ignore[assignment]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, settings.log_level))

    # Suppress noisy loggers
    for name in ("uvicorn.access", "aio_pika", "aiormq"):
        logging.getLogger(name).setLevel(logging.WARNING)


def setup_observability(service_name: str) -> None:
    """One-call setup for tracing, metrics, and logging."""
    setup_logging(service_name)
    setup_tracing(service_name)
    setup_metrics(service_name)


def instrument_fastapi(app: Any) -> None:
    """Instrument a FastAPI app for automatic tracing."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError as exc:
        raise ImportError(
            "opentelemetry-instrumentation-fastapi is required for FastAPI instrumentation. "
            "Install it in services that use `instrument_fastapi`."
        ) from exc

    FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]


# ── Custom Metrics ───────────────────────────────────────
def get_meter(name: str = "rag.platform") -> metrics.Meter:
    """Get a named meter for custom metrics."""
    return metrics.get_meter(name)


def create_request_metrics(meter: metrics.Meter) -> dict[str, Any]:
    """Create standard request metrics (counter, histogram, gauge)."""
    return {
        "request_count": meter.create_counter(
            "http_requests_total",
            description="Total HTTP requests",
            unit="1",
        ),
        "request_duration": meter.create_histogram(
            "http_request_duration_seconds",
            description="HTTP request duration in seconds",
            unit="s",
        ),
        "active_requests": meter.create_up_down_counter(
            "http_active_requests",
            description="Number of active HTTP requests",
            unit="1",
        ),
    }
