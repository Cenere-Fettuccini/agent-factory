"""OpenTelemetry wiring: OpenInference attribute names, tracer init, redaction.

No exporter is imported here. Host apps wire OTLP/Logfire/etc. themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan, Span

    from agentfactory.agent import Agent


# --- OpenInference semantic-convention attribute names -----------------------

SPAN_KIND = "openinference.span.kind"
INPUT_VALUE = "input.value"
OUTPUT_VALUE = "output.value"
LLM_MODEL_NAME = "llm.model_name"
LLM_TOKEN_COUNT_PROMPT = "llm.token_count.prompt"
LLM_TOKEN_COUNT_COMPLETION = "llm.token_count.completion"
LLM_TOKEN_COUNT_TOTAL = "llm.token_count.total"
TOOL_NAME = "tool.name"
TOOL_PARAMETERS = "tool.parameters"

# Span-kind values.
KIND_AGENT = "AGENT"
KIND_LLM = "LLM"
KIND_TOOL = "TOOL"

# Our own namespace for layer-specific fields.
AF_POLICY_MAX_STEPS = "agentfactory.policy.max_steps"
AF_POLICY_TIMEOUT = "agentfactory.policy.timeout_seconds"
AF_ERROR_CLASS = "agentfactory.error.class"
AF_ERROR_ACTION = "agentfactory.error.action"

REDACTED = "<redacted>"


class RedactingSpanProcessor(SpanProcessor):
    """Masks the values of configured attribute keys when a span ends.

    Must be registered *before* any exporting processor so the redaction is
    visible to the exporter.
    """

    def __init__(self, redact_keys: list[str]) -> None:
        self._redact_keys = set(redact_keys)

    def on_start(self, span: Span, parent_context: object | None = None) -> None:  # noqa: D102
        return

    def on_end(self, span: ReadableSpan) -> None:
        if not self._redact_keys:
            return
        attrs = getattr(span, "_attributes", None)
        if not attrs:
            return
        for key in self._redact_keys:
            if key in attrs:
                attrs[key] = REDACTED

    def shutdown(self) -> None:  # noqa: D102
        return

    def force_flush(self, timeout_millis: int = 30_000) -> bool:  # noqa: D102
        return True


# Keyed by service name so multiple agents in one process share a provider.
_PROVIDERS: dict[str, TracerProvider] = {}


def init_tracer(agent: Agent) -> trace.Tracer:
    """Create or fetch a TracerProvider for the agent's service. Idempotent."""
    service_name = agent.telemetry.service_name or agent.identity.id
    provider = _PROVIDERS.get(service_name)
    if provider is None:
        attrs: dict[str, str] = {"service.name": service_name}
        attrs.update(agent.telemetry.resource_attrs)
        provider = TracerProvider(resource=Resource.create(attrs))
        if agent.telemetry.redact_keys:
            provider.add_span_processor(
                RedactingSpanProcessor(agent.telemetry.redact_keys)
            )
        _PROVIDERS[service_name] = provider
    return provider.get_tracer("agentfactory")


def reset_providers() -> None:
    """Drop cached providers. For tests."""
    _PROVIDERS.clear()
