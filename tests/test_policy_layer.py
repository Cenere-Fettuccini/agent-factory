"""Tests for Layer 5 — PolicyLayer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.core.catalog.io_lexicon import IOSchema
from agentfactory.core.catalog.models import CoreModel
from agentfactory.core.layers.policy import PolicyLayer, RateLimit, TimeBudget


def _pl(inp: IOSchema, out: IOSchema, **kw) -> PolicyLayer:
    defaults = dict(
        id="p", name="P", version="0.1.0", description="x",
        primary=CoreModel.HAIKU_4_5.value,
        input_schema=inp, output_schema=out,
    )
    defaults.update(kw)
    return PolicyLayer(**defaults)


def test_depth_zero_forbids_subagents(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="max_recursion_depth=0"):
        _pl(
            simple_input_schema, simple_output_schema,
            subagent_grants={"child-v1"},
            max_recursion_depth=0,
        )


def test_acl_must_subset_grants(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="not in tool_grants"):
        _pl(
            simple_input_schema, simple_output_schema,
            tool_grants={"read_file"},
            tool_acl={"alice": {"grep"}},
        )


def test_acl_caller_must_be_in_allowlist(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="not in caller_allowlist"):
        _pl(
            simple_input_schema, simple_output_schema,
            tool_grants={"read_file"},
            caller_allowlist={"alice"},
            tool_acl={"bob": {"read_file"}},
        )


def test_allowed_tools_for_caller(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = _pl(
        simple_input_schema, simple_output_schema,
        tool_grants={"read_file", "grep"},
        caller_allowlist={"alice", "bob"},
        tool_acl={"bob": {"read_file"}},
    )
    assert a.allowed_tools_for("alice") == {"read_file", "grep"}
    assert a.allowed_tools_for("bob") == {"read_file"}
    assert a.allowed_tools_for("stranger") == set()


def test_rate_limit_burst_ordering() -> None:
    with pytest.raises(ValidationError, match="burst"):
        RateLimit(max_calls=10, window_seconds=60, burst=5)


def test_time_budget_ordering() -> None:
    with pytest.raises(ValidationError, match="total_seconds"):
        TimeBudget(per_call_seconds=10, total_seconds=5)
