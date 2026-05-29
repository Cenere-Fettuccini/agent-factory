# AgentFactory — Era I Implementation Handoff

This document is the complete spec for an implementer agent to build **AgentFactory Era I** from a clean repo. The repo currently contains only `pyproject.toml`, this `docs/` folder, and `README.md`. Everything else must be created.

Read this whole doc before writing code. The "Decisions already made" section is non-negotiable; do not relitigate it.

---

## 1. What we are building

A Python library that makes "is this an agent?" a framework-wide yes/no, and makes misconfiguration impossible at construction time.

An **Agent** is a **frozen, typed contract** composed of six layer sub-models plus an identity block. The contract is declarative — it can be serialized, diffed, code-reviewed, and later visualized.

A **Runtime executor** compiles an `Agent` into a `pydantic_ai.Agent`, wraps the call in policy guards, error handling, and OpenTelemetry spans, and runs it.

Out of scope for Era I: FastAPI service, web UI, real exporters, multi-agent graphs. Those are Eras II/III.

---

## 2. Decisions already made (do not change)

1. **Composition, not inheritance.** `Agent` is a frozen Pydantic model whose fields are layer instances. Layers are independent `BaseModel`s. Never chain layers via `class B(A)`. Rationale: inheritance caused validator name collisions in the previous attempt; composition isolates them and centralizes cross-layer rules in one `model_validator` on `Agent`.

2. **PydanticAI is a hard core dependency.** Do not write a `ModelClient` protocol. Do not write a tool-dispatch loop. The executor compiles our contract into `pydantic_ai.Agent` and delegates. Tests use `pydantic_ai.models.test.TestModel` / `FunctionModel`.

3. **OpenTelemetry is the only telemetry mechanism.** Layer is named `telemetry` (not `logging`). The framework depends on `opentelemetry-api` and `opentelemetry-sdk`. **No exporter is bundled** — apps wire OTLP/Logfire/Langfuse/Phoenix themselves. Span attributes follow **OpenInference semantic conventions** so downstream tracing backends work without translation.

4. **No FastAPI, no HTTP, no web deps in this package, ever.** Era I is a library.

5. **Catalogs are authoritative.** Every field that names a thing — model id, tool grant, error class, sink kind, IO type — is validated against a registry at construction. If it isn't catalogued, it doesn't exist.

6. **Construction-time failures, not runtime failures.** Builder/Agent construction must reject misconfiguration before the first call. Runtime errors should only come from genuinely runtime conditions (network, tool exceptions, policy limit exceeded).

---

## 3. Package layout

Create exactly this tree. File-level responsibilities follow.

```
agentfactory/
  __init__.py
  base.py
  envelope.py
  agent.py
  builder.py
  catalog/
    __init__.py
    registry.py
    models.py
    io_types.py
    tools.py
    errors.py
    sinks.py
  layers/
    __init__.py
    model.py
    io.py
    tools.py
    policy.py
    errors.py
    telemetry.py
  runtime/
    __init__.py
    executor.py
    otel.py
tests/
  __init__.py
  conftest.py
  test_registry.py
  test_catalogs.py
  test_layer_model.py
  test_layer_io.py
  test_layer_tools.py
  test_layer_policy.py
  test_layer_errors.py
  test_layer_telemetry.py
  test_agent.py
  test_builder.py
  test_envelope.py
  test_executor.py
  test_otel.py
```

---

## 4. File-by-file responsibilities

### `agentfactory/__init__.py`
Re-export the public surface: `Agent`, `AgentBuilder`. Nothing else. Trigger catalog default seeding on import.

### `agentfactory/base.py`
`Identity(BaseModel)`: frozen. Fields: `id: str`, `name: str`, `version: str`, `description: str`, `tags: list[str] = []`. Validate `id` matches `^[a-z][a-z0-9_-]*$`. No methods.

### `agentfactory/catalog/registry.py`
`Registry[T]`: a typed, in-memory registry keyed by string id. Operations: `register(id, spec)`, `get(id) -> T`, `contains(id) -> bool`, `ids() -> list[str]`, `clear()`. Raise `UnknownCatalogEntry` from `get` when missing. Generic over the spec type.

### `agentfactory/catalog/models.py`
`ModelSpec`: `id`, `provider` (literal: `"anthropic" | "openai" | "test"`), `provider_model_id`, `context_window: int`, `supports_tools: bool`.
Module-level `MODELS: Registry[ModelSpec]`. `seed_defaults()` registers at minimum:
- `anthropic:claude-opus-4-7`
- `anthropic:claude-sonnet-4-6`
- `anthropic:claude-haiku-4-5`
- `test:echo` (used by tests; maps to `TestModel`)

Provide `build_pydantic_ai_model(spec) -> pydantic_ai.models.Model`. Switch on `provider`.

### `agentfactory/catalog/io_types.py`
A lexicon of named primitive types (`text`, `json`, `number`, `bool`, `image_url`, `enum`) that `IOSchema` field specs reference. Each entry maps to a Python/Pydantic type. `IO_TYPES: Registry[IOTypeSpec]`.

### `agentfactory/catalog/tools.py`
`ToolSpec`: `id`, `description`, `arg_schema: type[BaseModel]`, `return_schema: type[BaseModel] | None`, `callable: Callable[..., Any]`. `TOOLS: Registry[ToolSpec]`. Empty by default; tests register their own.

### `agentfactory/catalog/errors.py`
`ErrorClassSpec`: `id`, `description`, `default_action: Literal["raise","retry","log"]`. `ERRORS: Registry[ErrorClassSpec]`. Seed: `tool_failure`, `model_timeout`, `policy_exceeded`, `validation_failure`, `unknown`.

### `agentfactory/catalog/sinks.py`
`SinkSpec`: `id`, `kind: Literal["otlp_http","otlp_grpc","console","noop"]`, `endpoint: str | None`. `SINKS: Registry[SinkSpec]`. Seed `console` and `noop`. **Do not import any exporter package** — sinks are descriptive only; wiring happens in the host app.

### `agentfactory/layers/model.py`
`ModelLayer(BaseModel, frozen=True)`:
- `model_id: str` — must be in `MODELS`.
- `temperature: float = 0.7` — 0–2.
- `max_output_tokens: int | None = None`.
- `system_prompt: str | None = None`.
Validators stay inside this class — no name leakage.

### `agentfactory/layers/io.py`
`IOFieldSpec`: `type_key: str` (must be in `IO_TYPES`), `required: bool = True`, `description: str = ""`.
`IOSchema`: `name: str`, `fields: dict[str, IOFieldSpec]`. Provides `to_pydantic_model() -> type[BaseModel]` that builds a Pydantic model dynamically (use `create_model`).
`IOLayer(BaseModel, frozen=True)`: `input_schema: IOSchema`, `output_schema: IOSchema`.

### `agentfactory/layers/tools.py`
`ToolsLayer(BaseModel, frozen=True)`:
- `tool_grants: list[str] = []` — every id must be in `TOOLS`.
- `caller_allowlist: list[str] = []` — list of agent ids allowed to invoke this agent (used by Era II; Era I just stores).

### `agentfactory/layers/policy.py`
`PolicyLayer(BaseModel, frozen=True)`:
- `max_steps: int = 8` — ≥ 1.
- `max_tool_calls: int = 16`.
- `max_recursion_depth: int = 2`.
- `max_input_tokens: int | None = None`.
- `max_output_tokens: int | None = None`.
- `timeout_seconds: float = 60.0`.

### `agentfactory/layers/errors.py`
`ErrorPolicy`: `on: str` (must be in `ERRORS`), `action: Literal["raise","retry","log"]`, `max_retries: int = 0`.
`ErrorLayer(BaseModel, frozen=True)`: `policies: list[ErrorPolicy] = []`. Provide `.action_for(error_id) -> ErrorPolicy` falling back to the catalog default.

### `agentfactory/layers/telemetry.py`
`TelemetryLayer(BaseModel, frozen=True)`:
- `service_name: str` — defaults to agent id at Agent construction time (set via `model_validator` on `Agent`, not here).
- `resource_attrs: dict[str, str] = {}`.
- `redact_keys: list[str] = []` — span attribute keys whose values get masked to `"<redacted>"`.
- `sample_rate: float = 1.0` — 0–1.
- `sinks: list[str] = ["console"]` — every id must be in `SINKS`.

### `agentfactory/agent.py`
`Agent(BaseModel)`:
```
model_config = ConfigDict(frozen=True, extra="forbid")
identity:  Identity
model:     ModelLayer
io:        IOLayer
tools:     ToolsLayer  = ToolsLayer()
policy:    PolicyLayer = PolicyLayer()
errors:    ErrorLayer  = ErrorLayer()
telemetry: TelemetryLayer = TelemetryLayer()
```
One `@model_validator(mode="after")` for cross-layer rules:
- If `tools.tool_grants` non-empty, `MODELS[model.model_id].supports_tools` must be true.
- If `telemetry.service_name` is empty, default it to `identity.id` (use `object.__setattr__` since frozen; or build a copy).
- `policy.max_output_tokens`, if set, must be ≤ `MODELS[model.model_id].context_window`.

### `agentfactory/envelope.py`
`InputEnvelope`, `OutputEnvelope`: Pydantic models carrying `data: dict`, `metadata: dict`, plus `trace_id`, `parent_span_id`. Provide `validate_against(schema: IOSchema)` that builds the dynamic Pydantic model and validates `data`. Raises `EnvelopeValidationError`.

### `agentfactory/builder.py`
`AgentBuilder(id, name, version, description, tags=None)`. Fluent methods, order-free, last-write-wins:
- `.with_model(model_id, *, temperature=..., ...) -> self`
- `.with_io(input_schema=..., output_schema=...) -> self`
- `.with_tools(grants=[...], caller_allowlist=[...]) -> self`
- `.with_policy(**fields) -> self`
- `.with_errors(policies=[...]) -> self`
- `.with_telemetry(**fields) -> self`
- `.build() -> Agent` — raises if required layers (`model`, `io`) were never set.

### `agentfactory/runtime/otel.py`
- `init_tracer(agent: Agent) -> trace.Tracer` — creates (or fetches) a `TracerProvider` keyed by `telemetry.service_name`, applies `resource_attrs`. Returns a tracer. **Idempotent** — multiple agents in one process share providers.
- A `SpanProcessor` subclass that redacts attribute keys listed in `telemetry.redact_keys`.
- Constants module defining **OpenInference attribute names** we use:
  - `openinference.span.kind` (values: `"AGENT"`, `"LLM"`, `"TOOL"`)
  - `input.value`, `output.value`
  - `llm.model_name`, `llm.token_count.prompt`, `llm.token_count.completion`, `llm.token_count.total`
  - `tool.name`, `tool.parameters`
  - Plus our own `agentfactory.*` namespace for layer-specific fields (e.g. `agentfactory.policy.max_steps`).

### `agentfactory/runtime/executor.py`
- `compile(agent: Agent) -> pydantic_ai.Agent` — builds the PydanticAI agent: model via `build_pydantic_ai_model`, system prompt from `model.system_prompt`, `result_type` from `agent.io.output_schema.to_pydantic_model()`, every tool in `tools.tool_grants` registered via `tool_plain`. Settings carry `temperature`, `max_output_tokens`, `usage_limits` from policy.
- `async def run(agent: Agent, input_data: dict, *, deps=None) -> OutputEnvelope` — the full call path:
  1. Open `agent.run` span (kind `AGENT`).
  2. Validate input via `InputEnvelope.validate_against(io.input_schema)`. Span attr `input.value`.
  3. Compile (cache by `agent.identity.id` + version).
  4. Apply policy: enforce `timeout_seconds` via `asyncio.wait_for`; pass `usage_limits` through.
  5. Wrap PydanticAI call. On exception, classify via `ErrorLayer.action_for(...)`; retry up to `max_retries`; on terminal failure, record exception on span, then raise or return per the action.
  6. Validate output against `io.output_schema`. Span attr `output.value`.
  7. Emit `llm.token_count.*` from the PydanticAI usage result.
  8. Return `OutputEnvelope`.
- A sync wrapper `run_sync(...)`.

---

## 5. Dependency manifest (pyproject)

Update `pyproject.toml`:

```toml
dependencies = [
  "pydantic>=2.6",
  "pydantic-ai>=0.0.14",        # use whatever current minor is
  "opentelemetry-api>=1.25",
  "opentelemetry-sdk>=1.25",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "ruff>=0.5",
  "mypy>=1.10",
]
```

Drop the `studio`, `fastapi`, `httpx` entries. They belong to Era II.

Add ruff + mypy config:
```toml
[tool.ruff]
line-length = 100
target-version = "py311"
[tool.ruff.lint]
select = ["E","F","I","UP","B","SIM"]

[tool.mypy]
strict = true
python_version = "3.11"
```

Keep `filterwarnings = ["error"]`.

---

## 6. Build order

Each step ends with green tests for that step. Do not move to the next step with red tests.

1. **base + registry** — `base.py`, `catalog/registry.py`, `test_registry.py`.
2. **catalogs** — all six catalog modules, default seeding, `test_catalogs.py`.
3. **layers** in this order, one PR-sized commit each: `model`, `io`, `tools`, `policy`, `errors`, `telemetry`. One test module per layer covering: happy path, every field validator, every catalog cross-check.
4. **agent.py** + `test_agent.py` — frozen, composition, the `_cross_layer` validator.
5. **envelope.py** + `test_envelope.py`.
6. **builder.py** + `test_builder.py` — order-free, last-write-wins, partial-then-complete, missing-required raises.
7. **runtime/otel.py** + `test_otel.py` — tracer idempotency, redaction processor.
8. **runtime/executor.py** + `test_executor.py` — use `TestModel` and `FunctionModel`; cover compile, run, timeout, retry, error classification, span emission, OpenInference attribute presence.

---

## 7. Acceptance criteria

The implementer is done when **all** of these hold:

1. `pip install -e ".[dev]"` succeeds on a clean venv.
2. `pytest` is green; `pytest -W error` is green (no surprise warnings).
3. `ruff check .` and `mypy agentfactory` are clean.
4. The README's quick-start snippet runs as written, with `TestModel` injected, and produces a validated `OutputEnvelope`.
5. No file in `agentfactory/` imports `fastapi`, `httpx`, `uvicorn`, or any specific OTel exporter package.
6. A failing field (e.g. unknown `model_id`, ungranted tool, output that doesn't match `output_schema`) raises **at the layer or agent construction step**, not inside `runtime.run`. The exception message names the offending field.
7. A real OTLP collector pointed at the host app (via standard OTel env vars) receives spans with OpenInference attribute names — verifiable by `print`-ing span dicts in a test that installs an in-memory exporter.

---

## 8. Conventions

- **Public API:** only `Agent`, `AgentBuilder` are re-exported from `agentfactory`. Everything else lives under explicit submodules.
- **Frozen everywhere:** every layer and `Agent` are `frozen=True, extra="forbid"`.
- **No magic strings in user code:** catalogs only. Internal code may use literals.
- **Errors:** subclasses of a single `AgentFactoryError`. Submodule-specific subclasses (`UnknownCatalogEntry`, `EnvelopeValidationError`, `PolicyExceeded`, etc.). Put them in the module that raises them; re-export the base from `agentfactory.__init__` if useful.
- **Async first:** `run` is async. `run_sync` is the wrapper. The compile step is sync.
- **Span names:** `agent.run`, `agent.model.invoke`, `agent.tool.<tool_id>`, `agent.policy.gate`. Snake-case via dots.

---

## 9. Out of scope for Era I (do not build)

- Any FastAPI/HTTP code.
- Any exporter (OTLP HTTP, OTLP gRPC, Logfire, Langfuse, Phoenix) — those are app-level wiring.
- Multi-agent graphs (`A calls B`), the Resolver, export-to-disk, dry-run-graph.
- Importing existing Langfuse-traced runs back into the contract.
- A CLI.
- Anything in `studio-web/`.

If you find yourself reaching for any of those, stop — it belongs to Era II or III.

---

## 10. Hand-off contract

When you finish, deliver:
- The full source tree per §3.
- All tests green per §7.
- One short `CHANGELOG.md` entry: "0.1.0 — Era I core: composition-based Agent contract over PydanticAI with native OTel/OpenInference."
- No edits to `docs/HANDOFF.md` or `docs/eras.html`.
