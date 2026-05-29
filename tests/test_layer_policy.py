"""Tests for PolicyLayer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.layers.policy import PolicyLayer


def test_defaults() -> None:
    p = PolicyLayer()
    assert p.max_steps == 8
    assert p.timeout_seconds == 60.0


@pytest.mark.parametrize("field", ["max_steps", "max_tool_calls", "max_recursion_depth"])
def test_counts_at_least_one(field: str) -> None:
    with pytest.raises(ValidationError):
        PolicyLayer(**{field: 0})


def test_timeout_positive() -> None:
    with pytest.raises(ValidationError, match="timeout_seconds"):
        PolicyLayer(timeout_seconds=0)


def test_optional_token_limits_positive() -> None:
    with pytest.raises(ValidationError):
        PolicyLayer(max_input_tokens=0)
    assert PolicyLayer(max_input_tokens=None).max_input_tokens is None
