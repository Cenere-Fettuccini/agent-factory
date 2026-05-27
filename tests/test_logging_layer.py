"""Tests for Layer 7 — LogLayer and sink catalog."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory import Agent
from agentfactory.core.catalog.io_lexicon import IOSchema
from agentfactory.core.catalog.models import CoreModel
from agentfactory.core.catalog.sinks import SINK_REGISTRY


def _agent(inp: IOSchema, out: IOSchema, **kw) -> Agent:
    defaults = dict(
        id="l", name="L", version="0.1.0", description="x",
        primary=CoreModel.HAIKU_4_5.value,
        input_schema=inp, output_schema=out,
    )
    defaults.update(kw)
    return Agent(**defaults)


def test_default_primary_sink_is_null(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = _agent(simple_input_schema, simple_output_schema)
    assert a.primary_sink == "null"
    assert a.active_sinks() == ("null",)


def test_unknown_sink_rejected(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="SINK_REGISTRY"):
        _agent(simple_input_schema, simple_output_schema, primary_sink="postgres")


def test_primary_must_not_appear_in_secondary(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="must not appear"):
        _agent(
            simple_input_schema, simple_output_schema,
            primary_sink="stdout", secondary_sinks=("stdout",),
        )


def test_secondary_duplicates_rejected(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        _agent(
            simple_input_schema, simple_output_schema,
            primary_sink="null",
            secondary_sinks=("stdout", "stdout"),
        )


def test_file_sink_requires_path_config(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="missing required"):
        _agent(simple_input_schema, simple_output_schema, primary_sink="file")


def test_file_sink_config_validated(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = _agent(
        simple_input_schema, simple_output_schema,
        primary_sink="file",
        sink_configs={"file": {"path": "/tmp/x.jsonl"}},
    )
    assert a.primary_sink == "file"


def test_config_for_inactive_sink_rejected(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="not in primary_sink"):
        _agent(
            simple_input_schema, simple_output_schema,
            primary_sink="null",
            sink_configs={"file": {"path": "/tmp/x"}},
        )


def test_config_free_sink_rejects_config(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="accepts no config"):
        _agent(
            simple_input_schema, simple_output_schema,
            primary_sink="stdout",
            sink_configs={"stdout": {"noise": 1}},
        )


def test_langfuse_requires_keys(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="missing required"):
        _agent(
            simple_input_schema, simple_output_schema,
            primary_sink="langfuse",
            sink_configs={"langfuse": {"public_key": "pk"}},  # secret missing
        )


def test_core_sinks_present() -> None:
    keys = SINK_REGISTRY.core_keys()
    assert "null" in keys
    assert "stdout" in keys
    assert "file" in keys
    assert "langfuse" in keys
