"""Tests for Layer 6 — ErrorLayer and error catalog."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.core.catalog.errors import ERROR_REGISTRY
from agentfactory.core.catalog.io_lexicon import IOSchema
from agentfactory.core.catalog.models import CoreModel
from agentfactory.core.layers.errors import (
    ErrorLayer,
    EscalationRule,
    PartialResultPolicy,
    RetryPolicy,
)


def _el(inp: IOSchema, out: IOSchema, **kw) -> ErrorLayer:
    defaults = dict(
        id="e", name="E", version="0.1.0", description="x",
        primary=CoreModel.HAIKU_4_5.value,
        input_schema=inp, output_schema=out,
    )
    defaults.update(kw)
    return ErrorLayer(**defaults)


def test_action_for_default_lookup(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = _el(simple_input_schema, simple_output_schema)
    assert a.action_for("validation_error") == "raise"


def test_action_for_retry_overrides_default(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = _el(
        simple_input_schema, simple_output_schema,
        retry_policies={"rate_limit": RetryPolicy()},
    )
    assert a.action_for("rate_limit") == "retry"


def test_action_for_escalation_overrides_default(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = _el(
        simple_input_schema, simple_output_schema,
        tool_grants={"human_review"},
        escalation_rules=(
            EscalationRule(trigger="tool_failure", action="human_review"),
        ),
    )
    assert a.action_for("tool_failure") == "human_review"


def test_retry_on_non_retryable_rejected(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="not retryable"):
        _el(
            simple_input_schema, simple_output_schema,
            retry_policies={"validation_error": RetryPolicy()},
        )


def test_human_review_requires_hitl_grant(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="HITL"):
        _el(
            simple_input_schema, simple_output_schema,
            tool_grants={"read_file"},
            escalation_rules=(
                EscalationRule(trigger="tool_failure", action="human_review"),
            ),
        )


def test_fallback_action_requires_fallback_agent(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="fallback_agent"):
        _el(
            simple_input_schema, simple_output_schema,
            escalation_rules=(
                EscalationRule(trigger="timeout", action="fallback"),
            ),
        )


def test_compensation_tool_must_be_granted(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="not in tool_grants"):
        _el(
            simple_input_schema, simple_output_schema,
            tool_grants={"read_file"},
            compensation_actions={"tool_failure": "grep"},
        )


def test_self_fallback_rejected(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    with pytest.raises(ValidationError, match="cannot be this agent"):
        _el(
            simple_input_schema, simple_output_schema,
            id="loop",
            fallback_agent="loop",
        )


def test_unknown_trigger_rejected() -> None:
    with pytest.raises(ValidationError, match="not in ERROR_REGISTRY"):
        EscalationRule(trigger="aurora_borealis", action="raise")


def test_meta_trigger_accepted() -> None:
    rule = EscalationRule(trigger="cycles_exceeded", action="raise")
    assert rule.trigger == "cycles_exceeded"


def test_partial_result_policy_enum(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = _el(
        simple_input_schema, simple_output_schema,
        partial_result_policy=PartialResultPolicy.RETURN_PARTIAL,
    )
    assert a.partial_result_policy is PartialResultPolicy.RETURN_PARTIAL


def test_retryable_classes_match_descriptor() -> None:
    assert ERROR_REGISTRY.get("rate_limit").retryable is True
    assert ERROR_REGISTRY.get("validation_error").retryable is False
