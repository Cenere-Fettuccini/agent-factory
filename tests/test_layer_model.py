"""Tests for ModelLayer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.layers.model import ModelLayer


def test_happy_path() -> None:
    layer = ModelLayer(model_id="test:echo", temperature=0.5)
    assert layer.model_id == "test:echo"
    assert layer.temperature == 0.5


def test_unknown_model_id_rejected() -> None:
    with pytest.raises(ValidationError, match="model catalog"):
        ModelLayer(model_id="nope:nope")


@pytest.mark.parametrize("temp", [-0.1, 2.1])
def test_temperature_out_of_range(temp: float) -> None:
    with pytest.raises(ValidationError, match="temperature"):
        ModelLayer(model_id="test:echo", temperature=temp)


def test_max_output_tokens_positive() -> None:
    with pytest.raises(ValidationError, match="max_output_tokens"):
        ModelLayer(model_id="test:echo", max_output_tokens=0)


def test_frozen() -> None:
    layer = ModelLayer(model_id="test:echo")
    with pytest.raises(ValidationError):
        layer.temperature = 0.1  # type: ignore[misc]


def test_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ModelLayer(model_id="test:echo", bogus=1)  # type: ignore[call-arg]
