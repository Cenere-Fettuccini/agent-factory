"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from agentfactory.core.catalog.io_lexicon import IOFieldSpec, IOSchema


@pytest.fixture
def simple_input_schema() -> IOSchema:
    return IOSchema(name="In", fields={"q": IOFieldSpec(type_key="text")})


@pytest.fixture
def simple_output_schema() -> IOSchema:
    return IOSchema(name="Out", fields={"a": IOFieldSpec(type_key="text")})
