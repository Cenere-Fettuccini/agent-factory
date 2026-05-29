"""Tests for IOFieldSpec, IOSchema, IOLayer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.layers.io import IOFieldSpec, IOLayer, IOSchema


def test_field_spec_unknown_type_rejected() -> None:
    with pytest.raises(ValidationError, match="IO type lexicon"):
        IOFieldSpec(type_key="nope")


def test_to_pydantic_model_required_and_optional() -> None:
    schema = IOSchema(
        name="In",
        fields={
            "q": IOFieldSpec(type_key="text"),
            "n": IOFieldSpec(type_key="number", required=False),
        },
    )
    model = schema.to_pydantic_model()
    inst = model(q="hi")
    assert inst.q == "hi"
    assert inst.n is None
    with pytest.raises(ValidationError):
        model(n=1.0)  # q is required


def test_io_layer_happy_path() -> None:
    in_s = IOSchema(name="In", fields={"q": IOFieldSpec(type_key="text")})
    out_s = IOSchema(name="Out", fields={"a": IOFieldSpec(type_key="text")})
    layer = IOLayer(input_schema=in_s, output_schema=out_s)
    assert layer.input_schema.name == "In"


def test_io_layer_frozen() -> None:
    in_s = IOSchema(name="In", fields={"q": IOFieldSpec(type_key="text")})
    out_s = IOSchema(name="Out", fields={"a": IOFieldSpec(type_key="text")})
    layer = IOLayer(input_schema=in_s, output_schema=out_s)
    with pytest.raises(ValidationError):
        layer.input_schema = out_s  # type: ignore[misc]
