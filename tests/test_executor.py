"""Tests for the runtime executor."""

from __future__ import annotations

from typing import Any

import pytest

from agentfactory import Agent
from agentfactory.core.catalog.io_lexicon import IOSchema
from agentfactory.core.catalog.models import CoreModel
from agentfactory.core.envelope import AgentError, AgentRequest, AgentResponse
from agentfactory.core.layers.errors import EscalationRule
from agentfactory.runtime import (
    AgentExecutor,
    ModelCallResult,
    NullSinkImpl,
    ToolCallResult,
)
from agentfactory.runtime.sinks import LangfuseSinkImpl


class StubModel:
    def __init__(self, replies: list[ModelCallResult]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model_key, messages, params, tools=None):
        self.calls.append({"model_key": model_key, "messages": messages})
        return self.replies.pop(0)


class StubDispatcher:
    def __init__(self, responses: dict[str, ToolCallResult]) -> None:
        self.responses = responses
        self.invocations: list[tuple[str, dict]] = []

    def call(self, *, tool_key, args):
        self.invocations.append((tool_key, args))
        return self.responses[tool_key]


def _agent(inp: IOSchema, out: IOSchema, **kw) -> Agent:
    defaults = dict(
        id="agent", name="A", version="0.1.0", description="x",
        primary=CoreModel.SONNET_4_6.value,
        input_schema=inp, output_schema=out,
    )
    defaults.update(kw)
    return Agent(**defaults)


def _req(agent_id: str = "agent", caller: str = "alice", **kw) -> AgentRequest:
    defaults = dict(
        target_agent_id=agent_id, caller_id=caller, payload={"q": "hello"}
    )
    defaults.update(kw)
    return AgentRequest(**defaults)


def test_happy_path_text_response(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    agent = _agent(simple_input_schema, simple_output_schema)
    ex = AgentExecutor(
        agent=agent,
        model_client=StubModel(
            [ModelCallResult(text="hi there", input_tokens=10, output_tokens=2, cost_usd=0.0001)]
        ),
        tool_dispatcher=StubDispatcher({}),
        sinks=[NullSinkImpl()],
    )
    resp = ex.run(_req())
    assert isinstance(resp, AgentResponse)
    assert resp.payload == {"a": "hi there"}
    assert resp.usage.cycles == 1
    assert resp.usage.model_calls == 1


def test_tool_dispatch_then_final_response(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    agent = _agent(
        simple_input_schema, simple_output_schema, tool_grants={"read_file"}
    )
    dispatcher = StubDispatcher(
        {"read_file": ToolCallResult(ok=True, value="contents", duration_ms=3)}
    )
    ex = AgentExecutor(
        agent=agent,
        model_client=StubModel([
            ModelCallResult(tool_calls=(("read_file", {"path": "/etc/hosts"}),)),
            ModelCallResult(text="I read it."),
        ]),
        tool_dispatcher=dispatcher,
        sinks=[NullSinkImpl()],
    )
    resp = ex.run(_req())
    assert isinstance(resp, AgentResponse)
    assert resp.usage.tool_calls == 1
    assert resp.usage.model_calls == 2
    assert dispatcher.invocations == [("read_file", {"path": "/etc/hosts"})]


def test_caller_allowlist_blocks(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    agent = _agent(
        simple_input_schema, simple_output_schema,
        caller_allowlist={"alice"},
    )
    ex = AgentExecutor(
        agent=agent,
        model_client=StubModel([]),
        tool_dispatcher=StubDispatcher({}),
        sinks=[NullSinkImpl()],
    )
    err = ex.run(_req(caller="eve"))
    assert isinstance(err, AgentError)
    assert err.error_class == "policy_violation"


def test_tool_acl_blocks(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    agent = _agent(
        simple_input_schema, simple_output_schema,
        tool_grants={"read_file", "grep"},
        caller_allowlist={"alice"},
        tool_acl={"alice": {"read_file"}},
    )
    ex = AgentExecutor(
        agent=agent,
        model_client=StubModel(
            [ModelCallResult(tool_calls=(("grep", {"pattern": "x"}),))]
        ),
        tool_dispatcher=StubDispatcher({}),
        sinks=[NullSinkImpl()],
    )
    err = ex.run(_req())
    assert isinstance(err, AgentError)
    assert err.error_class == "policy_violation"


def test_max_cycles_exhausted(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    agent = _agent(
        simple_input_schema, simple_output_schema,
        tool_grants={"read_file"},
        max_cycles=2,
    )
    ex = AgentExecutor(
        agent=agent,
        model_client=StubModel([
            ModelCallResult(tool_calls=(("read_file", {"path": "a"}),)),
            ModelCallResult(tool_calls=(("read_file", {"path": "b"}),)),
        ]),
        tool_dispatcher=StubDispatcher(
            {"read_file": ToolCallResult(ok=True, value="x")}
        ),
        sinks=[NullSinkImpl()],
    )
    err = ex.run(_req())
    assert isinstance(err, AgentError)
    assert err.error_class == "policy_violation"


def test_unknown_tool_call_blocked(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    agent = _agent(
        simple_input_schema, simple_output_schema, tool_grants={"read_file"}
    )
    ex = AgentExecutor(
        agent=agent,
        model_client=StubModel(
            [ModelCallResult(tool_calls=(("grep", {"pattern": "x"}),))]
        ),
        tool_dispatcher=StubDispatcher({}),
        sinks=[NullSinkImpl()],
    )
    err = ex.run(_req())
    assert isinstance(err, AgentError)
    assert err.error_class == "policy_violation"


def test_invalid_input_payload_returns_validation_error(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    agent = _agent(simple_input_schema, simple_output_schema)
    ex = AgentExecutor(
        agent=agent,
        model_client=StubModel([]),
        tool_dispatcher=StubDispatcher({}),
        sinks=[NullSinkImpl()],
    )
    err = ex.run(_req(payload={"wrong_field": "x"}))
    assert isinstance(err, AgentError)
    assert err.error_class == "validation_error"


def test_recursion_depth_overshoot_rejected(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    agent = _agent(
        simple_input_schema, simple_output_schema, max_recursion_depth=1
    )
    from agentfactory.runtime.executor import PolicyViolation
    with pytest.raises(PolicyViolation):
        AgentExecutor(
            agent=agent,
            model_client=StubModel([]),
            tool_dispatcher=StubDispatcher({}),
            sinks=[NullSinkImpl()],
            depth=2,
        )


def test_events_fan_out_to_sinks(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    sink = LangfuseSinkImpl(public_key="pk", secret_key="sk")
    agent = _agent(simple_input_schema, simple_output_schema)
    ex = AgentExecutor(
        agent=agent,
        model_client=StubModel(
            [ModelCallResult(text="ok", input_tokens=1, output_tokens=1, cost_usd=0.0)]
        ),
        tool_dispatcher=StubDispatcher({}),
        sinks=[sink],
    )
    ex.run(_req())
    kinds = [e["kind"] for e in sink.captured]
    assert "cycle" in kinds
    assert "model_call" in kinds


def test_hitl_emits_human_events(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    sink = LangfuseSinkImpl(public_key="pk", secret_key="sk")
    agent = _agent(
        simple_input_schema, simple_output_schema,
        tool_grants={"human_approve"},
        escalation_rules=(
            EscalationRule(trigger="tool_failure", action="human_review"),
        ),
    )
    # Need a tool grant for human_approve to satisfy the human_review
    # escalation precondition... actually the catalog tool is human_approve.
    # Let's add human_review too.
    agent = _agent(
        simple_input_schema, simple_output_schema,
        tool_grants={"human_approve", "human_review"},
        escalation_rules=(
            EscalationRule(trigger="tool_failure", action="human_review"),
        ),
    )
    ex = AgentExecutor(
        agent=agent,
        model_client=StubModel([
            ModelCallResult(tool_calls=(("human_approve", {"question": "ok?"}),)),
            ModelCallResult(text="done"),
        ]),
        tool_dispatcher=StubDispatcher(
            {"human_approve": ToolCallResult(ok=True, value={"choice": "yes"})}
        ),
        sinks=[sink],
    )
    resp = ex.run(_req())
    assert isinstance(resp, AgentResponse)
    kinds = [e["kind"] for e in sink.captured]
    assert "hitl" in kinds
    assert "tool_call" in kinds
    assert "tool_result" in kinds
