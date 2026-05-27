"""Tests for the fluent AgentBuilder."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory import Agent, AgentBuilder
from agentfactory.core.catalog.io_lexicon import IOSchema
from agentfactory.core.catalog.models import CoreModel
from agentfactory.core.layers.errors import EscalationRule, RetryPolicy


def test_minimal_build(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = (
        AgentBuilder("mini", name="Mini", version="0.1.0", description="x")
        .with_model(CoreModel.HAIKU_4_5.value)
        .with_io(input_schema=simple_input_schema, output_schema=simple_output_schema)
        .build()
    )
    assert isinstance(a, Agent)
    assert a.primary == CoreModel.HAIKU_4_5.value
    assert a.primary_sink == "null"


def test_full_build(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = (
        AgentBuilder("full", name="Full", version="0.1.0", description="x")
        .with_model(
            CoreModel.SONNET_4_6.value,
            fallback_chain=[CoreModel.HAIKU_4_5.value],
        )
        .with_io(input_schema=simple_input_schema, output_schema=simple_output_schema)
        .with_tools("read_file", "human_approve", aliases={"open": "read_file"})
        .with_policy(
            max_cycles=20, max_recursion_depth=0,
            cost_budget_usd=2.50,
            caller_allowlist={"alice"},
        )
        .with_errors(
            retry_policies={"rate_limit": RetryPolicy(max_attempts=5)},
            escalation_rules=[
                EscalationRule(trigger="tool_failure", action="human_review")
            ],
        )
        .with_logging("stdout")
        .build()
    )
    assert "read_file" in a.tool_grants
    assert a.aliases == {"open": "read_file"}
    assert a.max_cycles == 20
    assert "rate_limit" in a.retry_policies
    assert a.primary_sink == "stdout"


def test_method_chaining_returns_self() -> None:
    b = AgentBuilder("x", name="x", version="0.1.0", description="x")
    assert b.with_model(CoreModel.HAIKU_4_5.value) is b


def test_validation_runs_at_build(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    builder = (
        AgentBuilder("bad", name="Bad", version="0.1.0", description="x")
        .with_model("nonexistent-model")
        .with_io(input_schema=simple_input_schema, output_schema=simple_output_schema)
    )
    with pytest.raises(ValidationError):
        builder.build()


def test_regression_agent_rejects_bad_model_directly(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    """Regression: validator-name-collision bug allowed any model key to
    pass at the Agent (LogLayer) level even though ModelLayer rejected it.
    See feat/runtime commit 4e64ae9."""
    with pytest.raises(ValidationError, match="MODEL_REGISTRY"):
        Agent(
            id="bad", name="Bad", version="0.1.0", description="x",
            primary="never-existed",
            input_schema=simple_input_schema,
            output_schema=simple_output_schema,
        )


def test_regression_agent_runs_model_consistency(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    """Regression: ToolLayer._check_consistency was clobbering
    ModelLayer._check_consistency so primary-in-fallback was not caught
    at the Agent level."""
    with pytest.raises(ValidationError, match="must not appear"):
        Agent(
            id="dup", name="Dup", version="0.1.0", description="x",
            primary=CoreModel.OPUS_4_7.value,
            fallback_chain=[CoreModel.OPUS_4_7.value],
            input_schema=simple_input_schema,
            output_schema=simple_output_schema,
        )
