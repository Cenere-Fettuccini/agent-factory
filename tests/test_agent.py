"""Tests for the composed Agent contract and cross-layer validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.agent import Agent
from agentfactory.base import Identity
from agentfactory.layers.io import IOFieldSpec, IOLayer, IOSchema
from agentfactory.layers.model import ModelLayer
from agentfactory.layers.policy import PolicyLayer
from agentfactory.layers.telemetry import TelemetryLayer
from agentfactory.layers.tools import ToolsLayer


def _io() -> IOLayer:
    return IOLayer(
        input_schema=IOSchema(name="In", fields={"q": IOFieldSpec(type_key="text")}),
        output_schema=IOSchema(name="Out", fields={"a": IOFieldSpec(type_key="text")}),
    )


def _identity() -> Identity:
    return Identity(id="a1", name="A1", version="0.1.0", description="d")


def test_defaults_applied() -> None:
    agent = Agent(identity=_identity(), model=ModelLayer(model_id="test:echo"), io=_io())
    assert agent.policy.max_steps == 8
    assert agent.tools.tool_grants == []


def test_service_name_defaults_to_identity_id() -> None:
    agent = Agent(identity=_identity(), model=ModelLayer(model_id="test:echo"), io=_io())
    assert agent.telemetry.service_name == "a1"


def test_explicit_service_name_kept() -> None:
    agent = Agent(
        identity=_identity(),
        model=ModelLayer(model_id="test:echo"),
        io=_io(),
        telemetry=TelemetryLayer(service_name="custom"),
    )
    assert agent.telemetry.service_name == "custom"


def test_tools_require_supports_tools(echo_tool: str) -> None:
    # test:echo supports tools, so this should pass.
    agent = Agent(
        identity=_identity(),
        model=ModelLayer(model_id="test:echo"),
        io=_io(),
        tools=ToolsLayer(tool_grants=[echo_tool]),
    )
    assert agent.tools.tool_grants == ["echo"]


def test_max_output_tokens_within_context_window() -> None:
    with pytest.raises(ValidationError, match="context window"):
        Agent(
            identity=_identity(),
            model=ModelLayer(model_id="test:echo"),
            io=_io(),
            policy=PolicyLayer(max_output_tokens=10_000_000),
        )


def test_agent_frozen() -> None:
    agent = Agent(identity=_identity(), model=ModelLayer(model_id="test:echo"), io=_io())
    with pytest.raises(ValidationError):
        agent.policy = PolicyLayer()


def test_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        Agent(
            identity=_identity(),
            model=ModelLayer(model_id="test:echo"),
            io=_io(),
            bogus=1,  # type: ignore[call-arg]
        )
