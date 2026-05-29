"""Tests for TelemetryLayer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.layers.telemetry import TelemetryLayer


def test_defaults() -> None:
    t = TelemetryLayer()
    assert t.sinks == ["console"]
    assert t.sample_rate == 1.0
    assert t.service_name == ""


@pytest.mark.parametrize("rate", [-0.1, 1.1])
def test_sample_rate_range(rate: float) -> None:
    with pytest.raises(ValidationError, match="sample_rate"):
        TelemetryLayer(sample_rate=rate)


def test_unknown_sink_rejected() -> None:
    with pytest.raises(ValidationError, match="sink catalog"):
        TelemetryLayer(sinks=["mystery"])


def test_redact_keys_stored() -> None:
    t = TelemetryLayer(redact_keys=["input.value"])
    assert t.redact_keys == ["input.value"]
