# AgentFactory

AgentFactory makes an agent a **strongly-typed, definitive contract** — and then
gives you two ways to author networks of them: a backend you can drive directly,
and a visual canvas that exports a project which runs out of the box. It has
three parts, each a complete deliverable on its own:

1. **`agentfactory/` — the library.** A definitive, strongly-typed way to
   *define* an agent. Each agent knows exactly **what it connects to**, **who is
   allowed to connect to it**, **how it logs**, **how communication works**, and
   **what it has access to** — all settled at construction time, not discovered
   at runtime.
2. **`composer/` — the backend.** A stateless HTTP service for agent
   composition. The bundled frontend talks to it, but it stands alone: drive it
   from `curl`, a CI job, or a frontend you write yourself — anything that speaks
   HTTP can author agents against it.
3. **`studio-web/` — the frontend.** A strongly-typed visual canvas that
   comprehensively designs the agentic network and **exports it directly into a
   project that works out of the box**, with zero runtime dependency on the
   backend.

The chain only ever points one way: **library → backend → canvas**. The library
never imports the backend; the backend never imports the frontend.

## The contract (the library)

Built on [PydanticAI](https://ai.pydantic.dev/), with native
[OpenTelemetry](https://opentelemetry.io/) tracing using
[OpenInference](https://github.com/Arize-ai/openinference) semantic conventions.

An `Agent` is a **frozen, typed contract** composed of six layer sub-models plus
an identity block — together they pin down everything about how the agent
connects, communicates, and is observed:

```
identity → model → io → tools → policy → errors → telemetry
```

| Layer | What it nails down |
| --- | --- |
| `identity` | Who this agent is — `id`, `name`, `version`, `description`, `tags`. |
| `model` | Which catalogued model it runs on, and how it's prompted. |
| `io` | **How communication works** — the typed input/output schemas it speaks. |
| `tools` | **What it has access to** (`tool_grants`) and **who may call it** (`caller_allowlist`). |
| `policy` | The envelope it runs inside — timeouts, retries, token and recursion ceilings. |
| `errors` | How each error class is handled — raise, retry, or log. |
| `telemetry` | **How it logs** — service name, sinks, redaction, sampling. |

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

## Install with uv

```bash
uv sync --extra dev
```

Core dependencies: `pydantic`, `pydantic-ai`, `opentelemetry-api`,
`opentelemetry-sdk`. No FastAPI, no HTTP, no web — Era I is a library.

For the API layer, include the `api` extra too:

```bash
uv sync --extra dev --extra api
```

Run project commands through `uv` so they use the managed environment:

```bash
uv run pytest
uv run ruff check .
uv run mypy agentfactory
```

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

## AgentComposer API — the backend (Era II)

The backend for agent composition lives in the `composer/` package. It imports
the framework and exposes its catalogs, layer schemas, validation, and export
over HTTP — the framework never imports `composer`. The bundled `studio-web`
frontend is built on it, but it is **not coupled to any frontend**: author
directly from `curl`, a script, or your own UI — anything that speaks HTTP can
build agents against the same contract. Install the API extra and run it:

```bash
uv sync --extra api
uv run uvicorn composer.app:app --reload
```

Every request carries its own graph (nodes = agents, edges = "A calls B"); the
server holds no session state. Endpoints:

| Method & path | Purpose |
| --- | --- |
| `GET /node-types` | JSON Schema for every layer, derived live from the Pydantic classes |
| `GET /catalogs` | Every catalog (models, io_types, tools, errors, sinks) as JSON |
| `POST /graph/validate` | Structural validation — endpoints exist, recursion within limits |
| `POST /presets/resolve` | Fill unset fields from descriptions, propagate edge wiring |
| `POST /agents/preview` | Build one agent, return its frozen describe-output |
| `POST /export/dry-run` | Instantiate every agent in the graph in-memory |
| `POST /export` | Write a folder (frozen JSON + loader per agent + `__init__.py` + graph snapshot) |

The exported tree imports with only `agentfactory` installed — zero runtime
dependency on the API.

## Agent Studio UI — the frontend (Era III)

A strongly-typed, ComfyUI-style web canvas for visually designing **layered
agent networks** lives in `studio-web/`. Agents are arranged in horizontal
**tiers** (e.g. refinement → orchestrator → tools); a tier may only call the one
directly below it, so the path from a trigger to query resolution is explicit.
You set a model per agent and define tools on the tool tier — IO, wiring, and
caller permissions auto-resolve. The end result is **one click to export a
project that works out of the box**: an importable folder with zero runtime
dependency on the backend.

The UI is a thin shell over the AgentComposer API: no catalog value or layer
field is hardcoded, validation is the backend's, and `/export` owns the
filesystem. See [studio-web/README.md](studio-web/README.md) to run it.

### App startup script

Start the AgentComposer API and Agent Studio UI together from the repo root:

```bash
uv sync --extra api
uv run uvicorn composer.app:app --reload &
api_pid=$!
trap 'kill "$api_pid"' EXIT

(
  cd studio-web
  npm install
  npm run dev
)
```

Backend: `http://localhost:8000`
Frontend: `http://localhost:5173`

### Design with AI (in-browser)

The canvas has a **Design with AI** panel that turns a sentence into a starter
agent network. It runs a small language model **entirely in your browser** via
WebLLM — no server, no API key. The model drafts tiers, agents, and call edges;
the usual Resolve/Validate pipeline then fills and checks the rest.

No extra startup step — it ships with the frontend. Two things to know:

- Needs a **WebGPU** browser (desktop Chrome or Edge; the panel says so and
  disables itself otherwise).
- First use downloads the model from HuggingFace once (~1&nbsp;GB, shown with a
  progress bar), then caches it in the browser for instant, offline reuse.

## Out of scope (so far)

- Importing existing Langfuse-traced runs back into the contract.

See [docs/eras.html](docs/eras.html) for the full three-era roadmap.
