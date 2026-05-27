"""Tests for the typed messaging envelope."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from agentfactory.core.envelope import (
    AgentError,
    AgentEvent,
    AgentRequest,
    AgentResponse,
    BudgetEvent,
    CycleEvent,
    ErrorEvent,
    HITLEvent,
    ModelCallEvent,
    SpawnEvent,
    ToolCallEvent,
    ToolResultEvent,
    TraceContext,
    Usage,
)


def test_request_defaults_filled() -> None:
    req = AgentRequest(target_agent_id="demo")
    assert req.request_id
    assert req.caller_id == "anonymous"
    assert req.trace.trace_id
    assert req.trace.parent_span_id is None


def test_trace_child_propagation() -> None:
    parent = TraceContext()
    child = parent.child()
    assert child.trace_id == parent.trace_id
    assert child.parent_span_id == parent.span_id
    assert child.span_id != parent.span_id


def test_response_carries_usage() -> None:
    req = AgentRequest(target_agent_id="demo")
    resp = AgentResponse(
        request_id=req.request_id, agent_id="demo",
        payload={"a": "hi"}, trace=req.trace,
        usage=Usage(input_tokens=10, output_tokens=20, cost_usd=0.001),
    )
    assert resp.usage.input_tokens == 10
    assert resp.usage.output_tokens == 20


def test_error_carries_class_key() -> None:
    req = AgentRequest(target_agent_id="demo")
    err = AgentError(
        request_id=req.request_id, agent_id="demo",
        error_class="rate_limit", message="x", retryable=True, trace=req.trace,
    )
    assert err.error_class == "rate_limit"
    assert err.retryable is True


def test_immutability() -> None:
    req = AgentRequest(target_agent_id="demo")
    with pytest.raises(ValidationError):
        req.caller_id = "eve"  # type: ignore[misc]


@pytest.mark.parametrize(
    "event_kind, raw",
    [
        ("cycle", {"cycle_index": 0}),
        (
            "model_call",
            {
                "model_key": "claude-sonnet-4-6",
                "input_tokens": 5, "output_tokens": 5,
                "duration_ms": 100, "cost_usd": 0.0001,
            },
        ),
        ("tool_call", {"tool_key": "read_file", "args": {"path": "/a"}}),
        ("tool_result", {"tool_key": "read_file", "ok": True, "duration_ms": 5}),
        ("hitl", {"tool_key": "human_approve", "phase": "requested"}),
        (
            "budget",
            {
                "metric": "cost", "used": 0.5, "limit": 1.0,
                "threshold": "50pct",
            },
        ),
        (
            "spawn",
            {
                "child_agent_id": "child", "child_request_id": "rid",
                "depth": 1,
            },
        ),
        (
            "error",
            {"error_class": "rate_limit", "message": "x", "handled": True},
        ),
    ],
)
def test_event_discriminator_round_trip(event_kind: str, raw: dict) -> None:
    adapter = TypeAdapter(AgentEvent)
    trace = TraceContext()
    payload = {
        "kind": event_kind, "agent_id": "demo",
        "trace": trace.model_dump(mode="json"),
        **raw,
    }
    evt = adapter.validate_python(payload)
    assert evt.kind == event_kind


def test_event_unknown_kind_rejected() -> None:
    adapter = TypeAdapter(AgentEvent)
    trace = TraceContext()
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"kind": "mystery", "agent_id": "x", "trace": trace.model_dump()}
        )


@pytest.mark.parametrize(
    "cls",
    [
        CycleEvent, ModelCallEvent, ToolCallEvent, ToolResultEvent,
        HITLEvent, BudgetEvent, SpawnEvent, ErrorEvent,
    ],
)
def test_event_subclasses_carry_kind_literal(cls: type) -> None:
    # Every event class declares its `kind` as a Literal so the discriminator
    # works. Verify the class has a default value, not just a free string.
    field = cls.model_fields["kind"]
    assert field.default is not None
