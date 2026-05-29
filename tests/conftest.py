"""Shared fixtures: catalog seeding, a registered test tool, clean caches."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import BaseModel

import agentfactory.catalog as catalog
from agentfactory.builder import AgentBuilder
from agentfactory.catalog.tools import TOOLS, ToolSpec
from agentfactory.layers.io import IOFieldSpec, IOSchema
from agentfactory.runtime import otel
from agentfactory.runtime.executor import reset_compile_cache


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    """Ensure catalogs are seeded and runtime caches are clean per test."""
    catalog.seed_defaults()
    reset_compile_cache()
    otel.reset_providers()
    yield
    reset_compile_cache()
    otel.reset_providers()


class _EchoArgs(BaseModel):
    text: str


def _echo(text: str) -> str:
    return text


@pytest.fixture
def echo_tool() -> Iterator[str]:
    """Register an 'echo' tool for the duration of a test."""
    if not TOOLS.contains("echo"):
        TOOLS.register(
            "echo",
            ToolSpec(
                id="echo",
                description="Echoes its input.",
                arg_schema=_EchoArgs,
                callable=_echo,
            ),
        )
    yield "echo"
    TOOLS.clear()


@pytest.fixture
def simple_io() -> tuple[IOSchema, IOSchema]:
    return (
        IOSchema(name="In", fields={"q": IOFieldSpec(type_key="text")}),
        IOSchema(name="Out", fields={"a": IOFieldSpec(type_key="text")}),
    )


@pytest.fixture
def builder(simple_io: tuple[IOSchema, IOSchema]) -> AgentBuilder:
    in_schema, out_schema = simple_io
    return (
        AgentBuilder(
            id="tester", name="Tester", version="0.1.0", description="A test agent."
        )
        .with_model("test:echo")
        .with_io(input_schema=in_schema, output_schema=out_schema)
    )
