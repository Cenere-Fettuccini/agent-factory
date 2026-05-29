"""Tests for catalog seeding and contents."""

from __future__ import annotations

from agentfactory.catalog.errors import ERRORS
from agentfactory.catalog.io_types import IO_TYPES
from agentfactory.catalog.models import MODELS, build_pydantic_ai_model
from agentfactory.catalog.sinks import SINKS


def test_models_seeded() -> None:
    for mid in (
        "anthropic:claude-opus-4-7",
        "anthropic:claude-sonnet-4-6",
        "anthropic:claude-haiku-4-5",
        "test:echo",
    ):
        assert MODELS.contains(mid)


def test_io_types_seeded() -> None:
    for tid in ("text", "json", "number", "bool", "image_url", "enum"):
        assert IO_TYPES.contains(tid)


def test_errors_seeded() -> None:
    for eid in (
        "tool_failure",
        "model_timeout",
        "policy_exceeded",
        "validation_failure",
        "unknown",
    ):
        assert ERRORS.contains(eid)


def test_sinks_seeded() -> None:
    assert SINKS.contains("console")
    assert SINKS.contains("noop")


def test_build_test_model() -> None:
    from pydantic_ai.models.test import TestModel

    model = build_pydantic_ai_model(MODELS.get("test:echo"))
    assert isinstance(model, TestModel)
