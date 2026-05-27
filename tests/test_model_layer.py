"""Tests for Layer 2 — ModelLayer and routing policies."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.core.catalog.models import CoreModel
from agentfactory.core.layers.model import (
    CacheStrategy,
    CostBudgetRouting,
    GenerationParams,
    LatencyRouting,
    ModelLayer,
    SizeBasedRouting,
    StaticRouting,
)


def _ml(**kw) -> ModelLayer:
    defaults = dict(
        id="m", name="M", version="0.1.0", description="x",
        primary=CoreModel.SONNET_4_6.value,
    )
    defaults.update(kw)
    return ModelLayer(**defaults)


def test_default_routing_is_static() -> None:
    a = _ml()
    assert isinstance(a.routing_policy, StaticRouting)
    assert a.candidate_models() == (CoreModel.SONNET_4_6.value,)


def test_fallback_chain_appended_to_candidates() -> None:
    a = _ml(fallback_chain=[CoreModel.HAIKU_4_5.value])
    assert a.candidate_models() == (
        CoreModel.SONNET_4_6.value, CoreModel.HAIKU_4_5.value,
    )


def test_primary_in_fallback_rejected() -> None:
    with pytest.raises(ValidationError, match="must not appear"):
        _ml(
            primary=CoreModel.OPUS_4_7.value,
            fallback_chain=[CoreModel.OPUS_4_7.value],
        )


def test_unknown_primary_rejected() -> None:
    with pytest.raises(ValidationError, match="not in MODEL_REGISTRY"):
        _ml(primary="claude-vapor-9000")


def test_duplicate_fallback_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        _ml(
            primary=CoreModel.OPUS_4_7.value,
            fallback_chain=[CoreModel.HAIKU_4_5.value, CoreModel.HAIKU_4_5.value],
        )


def test_max_output_tokens_must_fit_context() -> None:
    with pytest.raises(ValidationError, match="exceeds primary model"):
        _ml(generation_params=GenerationParams(max_output_tokens=10_000_000))


def test_size_based_routing_targets_validated() -> None:
    with pytest.raises(ValidationError, match="not in MODEL_REGISTRY"):
        _ml(routing_policy=SizeBasedRouting(thresholds={0: "made-up"}))


def test_cost_routing_targets_validated() -> None:
    with pytest.raises(ValidationError, match="not in MODEL_REGISTRY"):
        _ml(routing_policy=CostBudgetRouting(escalation_order=("nope",)))


def test_latency_routing_target_validated() -> None:
    with pytest.raises(ValidationError, match="not in MODEL_REGISTRY"):
        _ml(routing_policy=LatencyRouting(fast_model="nope"))


def test_routing_discriminator_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        _ml(routing_policy={"kind": "nonsense"})  # type: ignore[arg-type]


def test_cache_strategy_enum() -> None:
    a = _ml(cache_strategy=CacheStrategy.EPHEMERAL_5MIN)
    assert a.cache_strategy is CacheStrategy.EPHEMERAL_5MIN


def test_generation_params_temperature_bounds() -> None:
    with pytest.raises(ValidationError):
        GenerationParams(temperature=3.0)
    with pytest.raises(ValidationError):
        GenerationParams(temperature=-0.1)
