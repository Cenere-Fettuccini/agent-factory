"""Tests for InputEnvelope / OutputEnvelope validation."""

from __future__ import annotations

import pytest

from agentfactory.envelope import (
    EnvelopeValidationError,
    InputEnvelope,
    OutputEnvelope,
)
from agentfactory.layers.io import IOFieldSpec, IOSchema


def _schema() -> IOSchema:
    return IOSchema(
        name="In",
        fields={
            "q": IOFieldSpec(type_key="text"),
            "n": IOFieldSpec(type_key="number", required=False),
        },
    )


def test_validate_against_success() -> None:
    env = InputEnvelope(data={"q": "hello"})
    coerced = env.validate_against(_schema())
    assert coerced["q"] == "hello"
    assert coerced["n"] is None


def test_validate_against_failure() -> None:
    env = InputEnvelope(data={"n": 1.0})  # missing required q
    with pytest.raises(EnvelopeValidationError, match="In"):
        env.validate_against(_schema())


def test_carries_trace_fields() -> None:
    env = OutputEnvelope(
        data={}, metadata={"k": "v"}, trace_id="t1", parent_span_id="s1"
    )
    assert env.trace_id == "t1"
    assert env.parent_span_id == "s1"
    assert env.metadata == {"k": "v"}
