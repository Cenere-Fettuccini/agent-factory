"""Compile an Agent contract into a PydanticAI agent and run it under policy."""

from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import json
from typing import TYPE_CHECKING, Any

from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel
from pydantic_ai import Agent as PydanticAIAgent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from agentfactory.base import AgentFactoryError
from agentfactory.catalog.models import MODELS, build_pydantic_ai_model
from agentfactory.catalog.tools import TOOLS
from agentfactory.envelope import (
    EnvelopeValidationError,
    InputEnvelope,
    OutputEnvelope,
)
from agentfactory.runtime import otel

if TYPE_CHECKING:
    from agentfactory.agent import Agent


class PolicyExceeded(AgentFactoryError):
    """Raised when a policy limit (timeout, usage) is exceeded at runtime."""


# compile cache keyed by identity id + version
_COMPILED: dict[tuple[str, str], PydanticAIAgent[Any, BaseModel]] = {}


class _ToolCallBudget:
    """Per-run counter for tool invocations (pydantic_ai dropped its own cap)."""

    __slots__ = ("limit", "count")

    def __init__(self, limit: int | None) -> None:
        self.limit = limit
        self.count = 0


# Set fresh by run() for each execution; wrapped tools charge against it.
_tool_call_budget: contextvars.ContextVar[_ToolCallBudget] = contextvars.ContextVar(
    "af_tool_call_budget", default=_ToolCallBudget(None)
)


def _wrap_tool_with_budget(func):
    """Wrap a tool callable so each call is charged against the per-run
    max_tool_calls budget, raising PolicyExceeded once the cap is exceeded.

    pydantic_ai removed its built-in per-tool-call limit, so we enforce it here.
    The signature/annotations of the original are preserved so pydantic_ai still
    builds the correct tool schema.
    """

    def _charge() -> None:
        budget = _tool_call_budget.get()
        if budget.limit is None:
            return
        budget.count += 1
        if budget.count > budget.limit:
            raise PolicyExceeded(f"max_tool_calls ({budget.limit}) exceeded")

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def awrapper(*args, **kwargs):
            _charge()
            return await func(*args, **kwargs)

        awrapper.__signature__ = inspect.signature(func)
        return awrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        _charge()
        return func(*args, **kwargs)

    wrapper.__signature__ = inspect.signature(func)
    return wrapper


def _classify(exc: BaseException) -> str:
    """Map a runtime exception to a catalogued error class id."""
    if isinstance(exc, asyncio.TimeoutError | TimeoutError):
        return "model_timeout"
    if isinstance(exc, UsageLimitExceeded):
        return "policy_exceeded"
    if isinstance(exc, EnvelopeValidationError):
        return "validation_failure"
    if isinstance(exc, PolicyExceeded):
        return "policy_exceeded"
    if isinstance(exc, AgentFactoryError):
        return "unknown"
    return "tool_failure"


def compile(agent: Agent) -> PydanticAIAgent[Any, BaseModel]:
    """Compile the contract into a PydanticAI agent. Cached by id+version."""
    key = (agent.identity.id, agent.identity.version)
    cached = _COMPILED.get(key)
    if cached is not None:
        return cached

    spec = MODELS.get(agent.model.model_id)
    model = build_pydantic_ai_model(spec)
    output_model = agent.io.output_schema.to_pydantic_model()

    settings = ModelSettings(temperature=agent.model.temperature)
    if agent.model.max_output_tokens is not None:
        settings["max_tokens"] = agent.model.max_output_tokens

    pai_agent = PydanticAIAgent(
        model=model,
        output_type=output_model,
        system_prompt=agent.model.system_prompt or "",
        model_settings=settings,
    )

    for tool_id in agent.tools.tool_grants:
        tool_spec = TOOLS.get(tool_id)
        pai_agent.tool_plain(_wrap_tool_with_budget(tool_spec.callable))

    _COMPILED[key] = pai_agent
    return pai_agent


def _usage_limits(agent: Agent) -> UsageLimits:
    # pydantic_ai's UsageLimits dropped the per-tool-call limit and renamed the
    # token fields, so max_tool_calls is enforced manually via _tool_call_budget
    # (max_steps still bounds the request loop).
    return UsageLimits(
        request_limit=agent.policy.max_steps,
        request_tokens_limit=agent.policy.max_input_tokens,
        response_tokens_limit=agent.policy.max_output_tokens,
    )


def reset_compile_cache() -> None:
    """Drop the compile cache. For tests."""
    _COMPILED.clear()


async def run(
    agent: Agent, input_data: dict[str, Any], *, deps: Any = None
) -> OutputEnvelope:
    """Run the agent end to end, under policy and telemetry."""
    tracer = otel.init_tracer(agent)

    with tracer.start_as_current_span("agent.run") as span:
        span.set_attribute(otel.SPAN_KIND, otel.KIND_AGENT)
        span.set_attribute(otel.LLM_MODEL_NAME, agent.model.model_id)
        span.set_attribute(otel.AF_POLICY_MAX_STEPS, agent.policy.max_steps)
        span.set_attribute(otel.AF_POLICY_TIMEOUT, agent.policy.timeout_seconds)

        # 1. Validate input.
        inbound = InputEnvelope(data=input_data)
        validated_input = inbound.validate_against(agent.io.input_schema)
        span.set_attribute(otel.INPUT_VALUE, json.dumps(validated_input, default=str))

        # 2. Compile (cached).
        pai_agent = compile(agent)
        limits = _usage_limits(agent)
        # Reset the per-run tool-call budget; wrapped tools charge against it
        # since pydantic_ai no longer enforces max_tool_calls itself.
        _tool_call_budget.set(_ToolCallBudget(agent.policy.max_tool_calls))
        prompt = json.dumps(validated_input, default=str)

        # 3 + 4. Run under timeout + usage limits, with error-policy retries.
        attempt = 0
        last_exc: BaseException | None = None
        while True:
            attempt += 1
            try:
                result = await asyncio.wait_for(
                    pai_agent.run(prompt, deps=deps, usage_limits=limits),
                    timeout=agent.policy.timeout_seconds,
                )
                break
            except Exception as exc:  # noqa: BLE001 — classify, then decide
                last_exc = exc
                error_id = _classify(exc)
                policy = agent.errors.action_for(error_id)
                span.set_attribute(otel.AF_ERROR_CLASS, error_id)
                span.set_attribute(otel.AF_ERROR_ACTION, policy.action)
                span.add_event(
                    "error", {"error.class": error_id, "exception": repr(exc)}
                )

                if policy.action == "retry" and attempt <= policy.max_retries:
                    continue

                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))

                if policy.action == "log":
                    return OutputEnvelope(
                        data={},
                        metadata={
                            "error_class": error_id,
                            "error": repr(exc),
                            "handled": "log",
                        },
                    )
                if error_id in ("model_timeout", "policy_exceeded"):
                    raise PolicyExceeded(str(exc)) from exc
                raise

        assert last_exc is None or result is not None  # noqa: S101

        # 5. Capture output and usage.
        output_data = result.output.model_dump()
        outbound = OutputEnvelope(data=output_data)
        outbound.validate_against(agent.io.output_schema)
        span.set_attribute(otel.OUTPUT_VALUE, json.dumps(output_data, default=str))

        usage = result.usage()
        if usage.request_tokens is not None:
            span.set_attribute(otel.LLM_TOKEN_COUNT_PROMPT, usage.request_tokens)
        if usage.response_tokens is not None:
            span.set_attribute(otel.LLM_TOKEN_COUNT_COMPLETION, usage.response_tokens)
        if usage.total_tokens is not None:
            span.set_attribute(otel.LLM_TOKEN_COUNT_TOTAL, usage.total_tokens)

        span.set_status(Status(StatusCode.OK))
        return outbound


def run_sync(
    agent: Agent, input_data: dict[str, Any], *, deps: Any = None
) -> OutputEnvelope:
    """Synchronous wrapper around :func:`run`."""
    return asyncio.run(run(agent, input_data, deps=deps))
