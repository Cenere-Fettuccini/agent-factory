"""Tests for Layer 3 — IOLayer and the IO lexicon."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.core.catalog.io_lexicon import IOFieldSpec, IOSchema, Message
from agentfactory.core.catalog.models import CoreModel
from agentfactory.core.layers.io import IOLayer, StreamingMode


def _io(io_in: IOSchema, io_out: IOSchema, **kw) -> IOLayer:
    defaults = dict(
        id="io", name="IO", version="0.1.0", description="x",
        primary=CoreModel.HAIKU_4_5.value,
        input_schema=io_in, output_schema=io_out,
    )
    defaults.update(kw)
    return IOLayer(**defaults)


def test_unknown_type_key_rejected() -> None:
    with pytest.raises(ValidationError, match="not in IO_REGISTRY"):
        IOSchema(name="bad", fields={"x": IOFieldSpec(type_key="moonbeam")})


def test_non_identifier_field_name_rejected() -> None:
    with pytest.raises(ValidationError, match="identifier"):
        IOSchema(name="bad", fields={"1bad": IOFieldSpec(type_key="text")})


def test_streaming_tokens_requires_text_output(
    simple_input_schema: IOSchema,
) -> None:
    out = IOSchema(
        name="OutNoText",
        fields={"d": IOFieldSpec(type_key="decision")},
    )
    with pytest.raises(ValidationError, match="text"):
        _io(simple_input_schema, out, streaming_mode=StreamingMode.TOKENS)


def test_streaming_tokens_accepts_text_output(
    simple_input_schema: IOSchema, simple_output_schema: IOSchema
) -> None:
    a = _io(simple_input_schema, simple_output_schema, streaming_mode=StreamingMode.TOKENS)
    assert a.streaming_mode is StreamingMode.TOKENS


def test_validate_payload_happy_path() -> None:
    inp = IOSchema(name="In", fields={
        "history": IOFieldSpec(type_key="message", repeated=True),
        "q": IOFieldSpec(type_key="text"),
    })
    payload = {
        "history": [{"role": "user", "content": "hi"}],
        "q": "follow up?",
    }
    out = inp.validate_payload(payload, strict=True)
    assert isinstance(out["history"][0], Message)
    assert out["q"] == "follow up?"


def test_validate_payload_strict_rejects_unknown() -> None:
    inp = IOSchema(name="In", fields={"q": IOFieldSpec(type_key="text")})
    with pytest.raises(ValueError, match="unknown fields"):
        inp.validate_payload({"q": "x", "extra": "no"}, strict=True)


def test_validate_payload_missing_required() -> None:
    inp = IOSchema(name="In", fields={"q": IOFieldSpec(type_key="text")})
    with pytest.raises(ValueError, match="missing required"):
        inp.validate_payload({}, strict=True)


def test_validate_payload_repeated_requires_list() -> None:
    inp = IOSchema(name="In", fields={
        "xs": IOFieldSpec(type_key="text", repeated=True),
    })
    with pytest.raises(TypeError, match="repeated"):
        inp.validate_payload({"xs": "not-a-list"}, strict=True)
