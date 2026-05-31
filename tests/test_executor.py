"""Tests for the runtime executor: compile, run, timeout, retry, telemetry."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic_ai import Agent as PydanticAIAgent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentfactory.agent import Agent
from agentfactory.base import Identity
from agentfactory.layers.errors import ErrorLayer, ErrorPolicy
from agentfactory.layers.io import IOFieldSpec, IOLayer, IOSchema
from agentfactory.layers.model import ModelLayer
from agentfactory.layers.policy import PolicyLayer
from agentfactory.runtime import executor, otel


def _agent(
    *,
    id: str = "exec1",
    policy: PolicyLayer | None = None,
    errors: ErrorLayer | None = None,
) -> Agent:
    return Agent(
        identity=Identity(id=id, name="E", version="0.1.0", description="d"),
        model=ModelLayer(model_id="test:echo"),
        io=IOLayer(
            input_schema=IOSchema(name="In", fields={"q": IOFieldSpec(type_key="text")}),
            output_schema=IOSchema(name="Out", fields={"a": IOFieldSpec(type_key="text")}),
        ),
        policy=policy or PolicyLayer(),
        errors=errors or ErrorLayer(),
    )


def test_compile_returns_pydantic_ai_agent() -> None:
    compiled = executor.compile(_agent())
    assert isinstance(compiled, PydanticAIAgent)


def test_compile_is_cached() -> None:
    a = _agent()
    assert executor.compile(a) is executor.compile(a)


def test_run_sync_happy_path() -> None:
    result = executor.run_sync(_agent(), {"q": "hello"})
    assert set(result.data.keys()) == {"a"}


async def test_run_validates_input() -> None:
    from agentfactory.envelope import EnvelopeValidationError

    with pytest.raises(EnvelopeValidationError):
        await executor.run(_agent(), {"wrong": "field"})


def test_timeout_raises_policy_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow(messages: Any, info: Any) -> ModelResponse:
        await asyncio.sleep(2)
        return ModelResponse(parts=[TextPart('{"a":"x"}')])

    monkeypatch.setattr(
        executor, "build_pydantic_ai_model", lambda spec: FunctionModel(slow)
    )
    agent = _agent(id="slow1", policy=PolicyLayer(timeout_seconds=0.2))
    with pytest.raises(executor.PolicyExceeded):
        executor.run_sync(agent, {"q": "hi"})


def test_retry_then_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def boom(messages: Any, info: Any) -> ModelResponse:
        calls["n"] += 1
        raise RuntimeError("kaboom")

    monkeypatch.setattr(
        executor, "build_pydantic_ai_model", lambda spec: FunctionModel(boom)
    )
    agent = _agent(
        id="boom1",
        errors=ErrorLayer(
            policies=[ErrorPolicy(on="tool_failure", action="retry", max_retries=2)]
        ),
    )
    with pytest.raises(RuntimeError, match="kaboom"):
        executor.run_sync(agent, {"q": "hi"})
    assert calls["n"] == 3  # initial + 2 retries


def test_log_action_returns_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(messages: Any, info: Any) -> ModelResponse:
        raise RuntimeError("logged")

    monkeypatch.setattr(
        executor, "build_pydantic_ai_model", lambda spec: FunctionModel(boom)
    )
    agent = _agent(
        id="log1",
        errors=ErrorLayer(policies=[ErrorPolicy(on="tool_failure", action="log")]),
    )
    result = executor.run_sync(agent, {"q": "hi"})
    assert result.metadata["error_class"] == "tool_failure"
    assert result.metadata["handled"] == "log"


def test_spans_carry_openinference_attributes() -> None:
    agent = _agent(id="span1")
    # Pre-create the provider so we can attach an in-memory exporter.
    otel.init_tracer(agent)
    provider = otel._PROVIDERS[agent.telemetry.service_name]
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    executor.run_sync(agent, {"q": "hello"})
    provider.force_flush()

    spans = {s.name: s for s in exporter.get_finished_spans()}
    run_span = spans["agent.run"]
    attrs = run_span.attributes
    assert attrs is not None
    assert attrs[otel.SPAN_KIND] == otel.KIND_AGENT
    assert attrs[otel.LLM_MODEL_NAME] == "test:echo"
    assert otel.INPUT_VALUE in attrs
    assert otel.OUTPUT_VALUE in attrs
    assert otel.LLM_TOKEN_COUNT_PROMPT in attrs
    assert otel.LLM_TOKEN_COUNT_TOTAL in attrs


def test_tool_call_budget_enforces_limit() -> None:
    """A wrapped tool raises PolicyExceeded once max_tool_calls is exceeded."""
    executor._tool_call_budget.set(executor._ToolCallBudget(2))

    def echo(x: int) -> int:
        return x

    wrapped = executor._wrap_tool_with_budget(echo)
    assert wrapped(1) == 1  # 1st call
    assert wrapped(2) == 2  # 2nd call
    with pytest.raises(executor.PolicyExceeded, match="max_tool_calls"):
        wrapped(3)  # 3rd call exceeds the cap of 2


def test_tool_call_budget_unlimited_when_none() -> None:
    """A None limit (max_tool_calls unset) means calls are never capped."""
    executor._tool_call_budget.set(executor._ToolCallBudget(None))

    def echo(x: int) -> int:
        return x

    wrapped = executor._wrap_tool_with_budget(echo)
    for i in range(50):
        assert wrapped(i) == i


def test_wrapped_tool_preserves_signature() -> None:
    """The wrapper keeps the original signature so pydantic_ai builds the schema."""
    import inspect

    def tool(city: str, days: int = 1) -> str:
        return f"{city}:{days}"

    wrapped = executor._wrap_tool_with_budget(tool)
    assert inspect.signature(wrapped) == inspect.signature(tool)
    assert wrapped.__name__ == "tool"


def test_per_tool_cap_enforced_independent_of_global_limit() -> None:
    """A per-tool cap bites even when the global max_tool_calls is unlimited."""
    executor._tool_call_budget.set(executor._ToolCallBudget(None))

    def echo(x: int) -> int:
        return x

    wrapped = executor._wrap_tool_with_budget(echo, "subagent.b", cap=2)
    assert wrapped(1) == 1
    assert wrapped(2) == 2
    with pytest.raises(executor.PolicyExceeded, match="call cap"):
        wrapped(3)


def test_recursion_guard_enforces_depth() -> None:
    """Nested runs past the entrypoint's max_recursion_depth raise PolicyExceeded."""
    agent = _agent(policy=PolicyLayer(max_recursion_depth=1))
    # depth 0 (entry) fixes the limit; depth 1 is the one allowed subagent level.
    with executor._recursion_guard(agent):
        with executor._recursion_guard(agent):
            with pytest.raises(executor.PolicyExceeded, match="max_recursion_depth"):
                with executor._recursion_guard(agent):
                    pass


async def test_async_tool_charged_against_budget() -> None:
    """Async tools are counted against the budget like sync ones."""
    executor._tool_call_budget.set(executor._ToolCallBudget(1))

    async def fetch(x: int) -> int:
        return x

    wrapped = executor._wrap_tool_with_budget(fetch)
    assert await wrapped(1) == 1
    with pytest.raises(executor.PolicyExceeded, match="max_tool_calls"):
        await wrapped(2)
