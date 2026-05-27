"""Layer 3 — IOLayer.

Adds typed input/output shape to ModelLayer. The shape is *composed* from the
IO lexicon (:mod:`agentfactory.core.catalog.io_lexicon`) — the layer references
lexicon entries by key, never by class. That keeps the wire format stable and
the schemas interoperable across agents.

``IOFieldSpec`` and ``IOSchema`` are defined in the lexicon module (they are
conceptually the top tier of the lexicon, alongside primitives and composites)
and re-exported here for convenience.

Slots:

* ``input_schema`` — required, defines what the agent accepts.
* ``output_schema`` — required, defines what the agent returns.
* ``strict`` — reject unknown fields at validation time.
* ``encoding`` — wire format for serialization (JSON / MSGPACK).
* ``streaming_mode`` — none / tokens / events.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import ConfigDict, Field, model_validator

# Re-exports: IOFieldSpec / IOSchema live in the catalog layer so downstream
# catalogs (tools, errors) can use them without depending on layer modules.
from agentfactory.core.catalog.io_lexicon import IOFieldSpec, IOSchema
from agentfactory.core.layers.model import ModelLayer

__all__ = [
    "IOFieldSpec",
    "IOSchema",
    "Encoding",
    "StreamingMode",
    "IOLayer",
]


class Encoding(StrEnum):
    JSON = "json"
    MSGPACK = "msgpack"


class StreamingMode(StrEnum):
    NONE = "none"
    TOKENS = "tokens"
    EVENTS = "events"


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
