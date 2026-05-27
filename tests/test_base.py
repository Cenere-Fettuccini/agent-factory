"""Tests for Layer 1 — BaseAgent."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.core.base import BaseAgent


def _base(**overrides) -> BaseAgent:
    defaults = dict(
        id="demo-agent",
        name="Demo",
        version="0.1.0",
        description="Demo agent.",
    )
    defaults.update(overrides)
    return BaseAgent(**defaults)


def test_construction_minimal() -> None:
    a = _base()
    assert a.id == "demo-agent"
    assert a.tags == frozenset()


def test_describe_format() -> None:
    a = _base()
    assert a.describe() == "demo-agent@0.1.0 — Demo"


def test_immutability() -> None:
    a = _base()
    with pytest.raises(ValidationError):
        a.name = "renamed"  # type: ignore[misc]


def test_with_tags_returns_copy() -> None:
    a = _base()
    b = a.with_tags("x", "y")
    assert a.tags == frozenset()
    assert b.tags == frozenset({"x", "y"})
    assert a is not b


@pytest.mark.parametrize("bad_id", ["UPPER", "-leading-dash", "1leading-digit", ""])
def test_id_pattern_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        _base(id=bad_id)


@pytest.mark.parametrize("bad_ver", ["1", "1.0", "1.0.0.0", "vee-one"])
def test_version_pattern_rejected(bad_ver: str) -> None:
    with pytest.raises(ValidationError):
        _base(version=bad_ver)


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        BaseAgent(
            id="demo", name="Demo", version="0.1.0",
            description="x", unknown_field="oops",  # type: ignore[call-arg]
        )
