"""Tests for OTel wiring: tracer idempotency and the redaction processor."""

from __future__ import annotations

from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from agentfactory.agent import Agent
from agentfactory.base import Identity
from agentfactory.layers.io import IOFieldSpec, IOLayer, IOSchema
from agentfactory.layers.model import ModelLayer
from agentfactory.layers.telemetry import TelemetryLayer
from agentfactory.runtime import otel


def _agent(redact: list[str] | None = None) -> Agent:
    return Agent(
        identity=Identity(id="otel1", name="O", version="0.1.0", description="d"),
        model=ModelLayer(model_id="test:echo"),
        io=IOLayer(
            input_schema=IOSchema(name="In", fields={"q": IOFieldSpec(type_key="text")}),
            output_schema=IOSchema(name="Out", fields={"a": IOFieldSpec(type_key="text")}),
        ),
        telemetry=TelemetryLayer(service_name="svc1", redact_keys=redact or []),
    )


def test_tracer_idempotent() -> None:
    a = _agent()
    otel.init_tracer(a)
    otel.init_tracer(a)
    # Same service name -> exactly one cached provider, shared across calls.
    assert len(otel._PROVIDERS) == 1
    assert otel.init_tracer(a) is not None


def test_redacting_processor_masks_exported_values() -> None:
    a = _agent(redact=["secret"])
    otel.init_tracer(a)  # creates provider + registers RedactingSpanProcessor
    provider = otel._PROVIDERS["svc1"]
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span("s") as span:
        span.set_attribute("secret", "classified")
        span.set_attribute("public", "ok")

    provider.force_flush()
    (exported,) = exporter.get_finished_spans()
    assert exported.attributes is not None
    assert exported.attributes["secret"] == otel.REDACTED
    assert exported.attributes["public"] == "ok"
