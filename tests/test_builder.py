"""Tests for the fluent AgentBuilder."""

from __future__ import annotations

import pytest

from agentfactory.builder import AgentBuilder, IncompleteAgentError
from agentfactory.layers.errors import ErrorPolicy
from agentfactory.layers.io import IOFieldSpec, IOSchema


def _schemas() -> tuple[IOSchema, IOSchema]:
    return (
        IOSchema(name="In", fields={"q": IOFieldSpec(type_key="text")}),
        IOSchema(name="Out", fields={"a": IOFieldSpec(type_key="text")}),
    )


def test_build_minimal(builder: AgentBuilder) -> None:
    agent = builder.build()
    assert agent.identity.id == "tester"
    assert agent.model.model_id == "test:echo"


def test_missing_model_raises() -> None:
    in_s, out_s = _schemas()
    b = AgentBuilder(id="x", name="X", version="0", description="d").with_io(
        input_schema=in_s, output_schema=out_s
    )
    with pytest.raises(IncompleteAgentError, match="model"):
        b.build()


def test_missing_io_raises() -> None:
    b = AgentBuilder(id="x", name="X", version="0", description="d").with_model(
        "test:echo"
    )
    with pytest.raises(IncompleteAgentError, match="io"):
        b.build()


def test_order_free_and_last_write_wins() -> None:
    in_s, out_s = _schemas()
    agent = (
        AgentBuilder(id="x", name="X", version="0", description="d")
        .with_policy(max_steps=2)
        .with_io(input_schema=in_s, output_schema=out_s)
        .with_model("test:echo", temperature=0.1)
        .with_model("test:echo", temperature=0.9)  # last write wins
        .build()
    )
    assert agent.model.temperature == 0.9
    assert agent.policy.max_steps == 2


def test_with_errors_and_telemetry(builder: AgentBuilder) -> None:
    agent = (
        builder.with_errors(
            policies=[ErrorPolicy(on="tool_failure", action="log")]
        )
        .with_telemetry(sample_rate=0.5)
        .build()
    )
    assert agent.errors.policies[0].action == "log"
    assert agent.telemetry.sample_rate == 0.5
