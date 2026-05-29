"""Tests for ErrorPolicy and ErrorLayer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.layers.errors import ErrorLayer, ErrorPolicy


def test_unknown_error_class_rejected() -> None:
    with pytest.raises(ValidationError, match="error catalog"):
        ErrorPolicy(on="not_a_class", action="raise")


def test_negative_retries_rejected() -> None:
    with pytest.raises(ValidationError, match="max_retries"):
        ErrorPolicy(on="tool_failure", action="retry", max_retries=-1)


def test_action_for_explicit_policy() -> None:
    layer = ErrorLayer(
        policies=[ErrorPolicy(on="tool_failure", action="retry", max_retries=3)]
    )
    resolved = layer.action_for("tool_failure")
    assert resolved.action == "retry"
    assert resolved.max_retries == 3


def test_action_for_falls_back_to_catalog_default() -> None:
    layer = ErrorLayer()
    resolved = layer.action_for("policy_exceeded")
    assert resolved.action == "raise"
    assert resolved.max_retries == 0
