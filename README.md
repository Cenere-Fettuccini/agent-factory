# AgentFactory

A typed, layered framework for building well-bounded agents on top of
[PydanticAI](https://ai.pydantic.dev/), with native
[OpenTelemetry](https://opentelemetry.io/) tracing using
[OpenInference](https://github.com/Arize-ai/openinference) semantic
conventions.

An `Agent` is a **frozen, typed contract** composed of six layer sub-models
plus an identity block:

```
identity → model → io → tools → policy → errors → telemetry
```

Each layer is an independent Pydantic model that validates its own fields and
cross-checks them against the framework's catalogs at construction time.
`Agent` itself is a composition of those layers — not a deep inheritance chain
— so validators stay isolated and cross-layer rules live in one explicit place.
Misconfiguration fails fast and loudly; runtime errors come only from
genuinely runtime conditions.

The runtime executor compiles an `Agent` into a `pydantic_ai.Agent`, wraps the
call in policy guards and error handling, and emits OTel spans tagged with
OpenInference attribute names. Wire any OTLP-compatible backend (Langfuse,
Phoenix, Arize, Logfire, Jaeger, …) at the host-app level — the framework
bundles no exporter.

## Install

```bash
pip install -e ".[dev]"
```

Core dependencies: `pydantic`, `pydantic-ai`, `opentelemetry-api`,
`opentelemetry-sdk`. No FastAPI, no HTTP, no web — Era I is a library.

## Quick start

```python
from agentfactory import AgentBuilder
from agentfactory.layers.io import IOFieldSpec, IOSchema
from agentfactory.runtime.executor import run_sync

agent = (
    AgentBuilder(
        id="summarizer",
        name="Summarizer",
        version="0.1.0",
        description="Summarises text.",
    )
    .with_model("anthropic:claude-haiku-4-5", temperature=0.3)
    .with_io(
        input_schema=IOSchema(
            name="In",
            fields={"q": IOFieldSpec(type_key="text")},
        ),
        output_schema=IOSchema(
            name="Out",
            fields={"a": IOFieldSpec(type_key="text")},
        ),
    )
    .with_policy(max_steps=4, timeout_seconds=20)
    .with_telemetry(service_name="summarizer", sinks=["console"])
    .build()
)

result = run_sync(agent, {"q": "Summarise the moon landings in two sentences."})
print(result.data["a"])
```

For tests, swap the model id for `"test:echo"` — it maps to
`pydantic_ai.models.test.TestModel`, so the executor runs end-to-end without a
network call.

## What the framework owns

- The **catalogs**: models, IO types, tools, error classes, sinks. Every field
  that names a thing is validated against its catalog at construction.
- The **contract**: a frozen, serialisable `Agent` value you can diff,
  code-review, and version.
- The **policy envelope**: timeouts, retries, token ceilings, recursion
  depth — enforced around the model call, not by the model.
- The **telemetry shape**: layer-aligned span names (`agent.run`,
  `agent.model.invoke`, `agent.tool.<id>`, `agent.policy.gate`) with
  OpenInference attribute names.

## What PydanticAI owns

- Provider clients (Anthropic, OpenAI, test models).
- Typed result parsing.
- Tool registration and dispatch.
- Streaming, message history, run context.

The executor's job is to compile our contract into a `pydantic_ai.Agent` and
delegate. We do not reimplement model or tool plumbing.

## Telemetry

The framework depends only on `opentelemetry-api` and `opentelemetry-sdk`. It
ships no exporter. To send traces somewhere:

```python
# host app, once at startup
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry import trace

trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="https://<your-collector>"))
)
```

Because span attributes follow OpenInference conventions, Langfuse, Phoenix,
Arize, and Logfire all render the spans natively — no translation layer.

## Out of scope (Era I)

- HTTP authoring service (Era II — `AgentComposer API`).
- Visual editor (Era III — `Agent Studio UI`).
- Multi-agent graph resolution, export-to-disk, dry-run-graph.
- Importing existing Langfuse-traced runs back into the contract.

See [docs/eras.html](docs/eras.html) for the full three-era roadmap. See
[docs/HANDOFF.md](docs/HANDOFF.md) for the implementation spec.
