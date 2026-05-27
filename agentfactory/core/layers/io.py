"""Layer 3 — IOLayer.

Adds typed input/output shape to ModelLayer. The shape is *composed* from the
IO lexicon (:mod:`agentfactory.core.catalog.io_lexicon`) — the layer references
lexicon entries by key, never by class. That keeps the wire format stable and
the schemas interoperable across agents.

Slots:

* ``input_schema`` — required, defines what the agent accepts.
* ``output_schema`` — required, defines what the agent returns.
* ``strict`` — reject unknown fields at validation time.
* ``encoding`` — wire format for serialization (JSON / MSGPACK).
* ``streaming_mode`` — none / tokens / events.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentfactory.core.catalog.io_lexicon import IO_REGISTRY
from agentfactory.core.layers.model import ModelLayer


# ---------------------------------------------------------------------------
# Schema composition
# ---------------------------------------------------------------------------


class IOFieldSpec(BaseModel):
    """One field in an IOSchema. References a lexicon type by key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type_key: str = Field(
        ...,
        description="Key into IO_REGISTRY identifying the value's IO type.",
    )
    required: bool = True
    repeated: bool = False
    nullable: bool = False
    description: str = Field(default="", max_length=512)

    @field_validator("type_key")
    @classmethod
    def _validate_type_key(cls, v: str) -> str:
        if not IO_REGISTRY.has(v):
            raise ValueError(
                f"IO type {v!r} is not in IO_REGISTRY "
                f"(core: {IO_REGISTRY.core_keys()}, "
                f"ext: {IO_REGISTRY.extension_keys()})"
            )
        return v


class IOSchema(BaseModel):
    """A named composition of IOFieldSpecs. Used for both input and output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., min_length=1, max_length=128)
    fields: dict[str, IOFieldSpec] = Field(..., min_length=1)

    @field_validator("fields")
    @classmethod
    def _validate_field_names(cls, v: dict[str, IOFieldSpec]) -> dict[str, IOFieldSpec]:
        for fname in v:
            if not fname or not fname.isidentifier():
                raise ValueError(
                    f"schema field name {fname!r} must be a valid Python identifier"
                )
        return v

    def validate_payload(self, payload: dict[str, Any], *, strict: bool) -> dict[str, Any]:
        """Validate a raw payload against this schema. Returns a coerced copy."""
        coerced: dict[str, Any] = {}
        for fname, spec in self.fields.items():
            if fname not in payload:
                if spec.required:
                    raise ValueError(f"missing required field {fname!r}")
                continue
            value = payload[fname]
            if value is None:
                if not spec.nullable:
                    raise ValueError(f"field {fname!r} is not nullable")
                coerced[fname] = None
                continue
            desc = IO_REGISTRY.get(spec.type_key)
            if spec.repeated:
                if not isinstance(value, (list, tuple)):
                    raise TypeError(
                        f"field {fname!r} is repeated; expected list, got "
                        f"{type(value).__name__}"
                    )
                coerced[fname] = [desc.validate_value(v) for v in value]
            else:
                coerced[fname] = desc.validate_value(value)
        if strict:
            unknown = set(payload) - set(self.fields)
            if unknown:
                raise ValueError(f"unknown fields in strict schema: {sorted(unknown)}")
        return coerced


# ---------------------------------------------------------------------------
# Layer enums
# ---------------------------------------------------------------------------


class Encoding(StrEnum):
    JSON = "json"
    MSGPACK = "msgpack"


class StreamingMode(StrEnum):
    NONE = "none"
    TOKENS = "tokens"
    EVENTS = "events"


# ---------------------------------------------------------------------------
# The layer
# ---------------------------------------------------------------------------


class IOLayer(ModelLayer):
    """Layer 3 — extends ModelLayer with input/output schema slots."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    input_schema: IOSchema
    output_schema: IOSchema
    strict: bool = Field(
        default=True,
        description="Reject unknown fields at validation time.",
    )
    encoding: Encoding = Field(default=Encoding.JSON)
    streaming_mode: StreamingMode = Field(default=StreamingMode.NONE)

    @model_validator(mode="after")
    def _check_streaming_against_output(self) -> Self:
        # Token streaming only makes sense for outputs containing a text field.
        if self.streaming_mode is StreamingMode.TOKENS:
            text_fields = [
                fname
                for fname, spec in self.output_schema.fields.items()
                if spec.type_key == "text" and not spec.repeated
            ]
            if not text_fields:
                raise ValueError(
                    "streaming_mode=TOKENS requires the output schema to "
                    "contain at least one scalar 'text' field"
                )
        return self
