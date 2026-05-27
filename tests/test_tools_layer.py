"""Tests for Layer 4 — ToolLayer and tool catalog."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.core.catalog.io_lexicon import IOSchema
from agentfactory.core.catalog.models import CoreModel
from agentfactory.core.catalog.tools import TOOL_REGISTRY
from agentfactory.core.layers.tools import ToolLayer


def _tl(inp: IOSchema, out: IOSchema, **kw) -> ToolLayer:
    defaults = dict(
        id="t", name="T", version="0.1.0", description="x",
        primary=CoreModel.HAIKU_4_5.value,
        input_schema=inp, output_schema=out,
    )
    defaults.update(kw)
    return ToolLayer(**defaults)


def test_hitl_split(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = _tl(
        simple_input_schema, simple_output_schema,
        tool_grants={"read_file", "human_approve", "human_input"},
    )
    assert a.hitl_grants() == {"human_approve", "human_input"}
    assert a.non_hitl_grants() == {"read_file"}


def test_declared_side_effects(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = _tl(
        simple_input_schema, simple_output_schema,
        tool_grants={"read_file", "human_approve"},
    )
    assert a.declared_side_effects() == {"read_fs", "human_io"}


def test_unknown_tool_rejected(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="TOOL_REGISTRY"):
        _tl(simple_input_schema, simple_output_schema, tool_grants={"launch_missiles"})


def test_alias_target_validated(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="unknown tool"):
        _tl(
            simple_input_schema, simple_output_schema,
            aliases={"find": "nonexistent"},
        )


def test_alias_cannot_shadow_tool_key(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="collides"):
        _tl(
            simple_input_schema, simple_output_schema,
            aliases={"grep": "read_file"},
        )


def test_default_for_non_granted_tool_rejected(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="not in tool_grants"):
        _tl(
            simple_input_schema, simple_output_schema,
            tool_grants={"read_file"},
            defaults={"grep": {"pattern": "x"}},
        )


def test_default_with_unknown_parameter_rejected(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="unknown"):
        _tl(
            simple_input_schema, simple_output_schema,
            tool_grants={"grep"},
            defaults={"grep": {"bogus": "x"}},
        )


def test_descriptor_marks_hitl_tools() -> None:
    assert TOOL_REGISTRY.get("human_review").requires_human is True
    assert TOOL_REGISTRY.get("read_file").requires_human is False
