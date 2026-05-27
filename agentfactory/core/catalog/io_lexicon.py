"""Core IO lexicon.

A standardized vocabulary for what flows in and out of agents. Modelled after
the layers of natural language:

* **Primitives** (phonemes): atomic value types — text, number, boolean,
  json, file ref, image ref.
* **Composites** (morphemes): structured units assembled from primitives —
  Message, Decision, ToolCall, ToolResult, Citation.
* **Schemas** (sentences): :class:`IOFieldSpec` and :class:`IOSchema` —
  composition surfaces that reference primitives/composites by key.

All three tiers live in the catalog layer so that downstream catalogs (tools,
errors, sinks) can use schemas without depending on layer modules. Layers
re-export the schema types for convenience.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentfactory.core.registry import Registry


# ---------------------------------------------------------------------------
# Composites — concrete Pydantic models for the standard structured types
# ---------------------------------------------------------------------------


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Message(_ImmutableModel):
    """A single conversational turn."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    timestamp: datetime | None = None
    name: str | None = None


class Decision(_ImmutableModel):
    """A discrete branching choice produced by an agent."""

    choice: str
    rationale: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ToolCall(_ImmutableModel):
    """A request from an agent to invoke a tool."""

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None


class ToolResult(_ImmutableModel):
    """The outcome of a tool invocation, paired with its originating call."""

    call_id: str
    ok: bool
    value: Any = None
    error: str | None = None


class Citation(_ImmutableModel):
    """A grounded reference to source material."""

    source: str
    locator: str = ""
    excerpt: str = ""


# ---------------------------------------------------------------------------
# Descriptor — the catalog component
# ---------------------------------------------------------------------------


_PRIMITIVE_BACKINGS: Final[dict[str, type]] = {
    "text": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "json": dict,
    "file_ref": str,
    "image_ref": str,
}


class IOTypeDescriptor(BaseModel):
    """One entry in the IO lexicon.

    ``level`` distinguishes ``primitive`` (a wrapped scalar) from ``composite``
    (a Pydantic model). The framework validates values by looking up the
    descriptor and applying its backing type; downstream code never needs to
    touch the underlying class directly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["io"] = "io"
    key: str = Field(..., min_length=1, max_length=64)
    level: Literal["primitive", "composite"]
    description: str = Field(default="", max_length=512)

    # Backing type stored as a class reference. Frozen via model_config and
    # arbitrary_types_allowed to admit Python ``type`` objects.
    backing: type

    # Sealed set of allowed primitive backings — guards extension registrations
    # that try to claim ``level='primitive'`` with an arbitrary class.
    _ALLOWED_PRIMITIVES: ClassVar[frozenset[str]] = frozenset(_PRIMITIVE_BACKINGS)

    def validate_value(self, value: Any) -> Any:
        """Coerce/validate a raw value against this descriptor. Raises on failure."""
        if self.level == "primitive":
            if not isinstance(value, self.backing):
                raise TypeError(
                    f"value {value!r} is not a {self.backing.__name__} "
                    f"(IO type {self.key!r})"
                )
            return value
        # Composite path: rely on the backing Pydantic model.
        if isinstance(value, self.backing):
            return value
        if isinstance(value, dict):
            return self.backing.model_validate(value)
        raise TypeError(
            f"composite IO type {self.key!r} expected a "
            f"{self.backing.__name__} or dict, got {type(value).__name__}"
        )


IO_REGISTRY: Final[Registry[IOTypeDescriptor]] = Registry(
    kind="io", component_type=IOTypeDescriptor
)


def _bootstrap_core() -> None:
    for key, py_type in _PRIMITIVE_BACKINGS.items():
        IO_REGISTRY._register_core(
            IOTypeDescriptor(
                key=key,
                level="primitive",
                backing=py_type,
                description=f"Primitive {key} value.",
            )
        )

    composites: tuple[tuple[str, type[BaseModel], str], ...] = (
        ("message", Message, "A single conversational turn."),
        ("decision", Decision, "A discrete branching choice."),
        ("tool_call", ToolCall, "A request to invoke a tool."),
        ("tool_result", ToolResult, "The outcome of a tool invocation."),
        ("citation", Citation, "A grounded reference to source material."),
    )
    for key, cls, desc in composites:
        IO_REGISTRY._register_core(
            IOTypeDescriptor(
                key=key, level="composite", backing=cls, description=desc
            )
        )
    IO_REGISTRY.seal_core()


_bootstrap_core()


# ---------------------------------------------------------------------------
# Schema composition (top tier of the lexicon)
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
    def _validate_field_names(
        cls, v: dict[str, IOFieldSpec]
    ) -> dict[str, IOFieldSpec]:
        for fname in v:
            if not fname or not fname.isidentifier():
                raise ValueError(
                    f"schema field name {fname!r} must be a valid Python identifier"
                )
        return v

    def validate_payload(
        self, payload: dict[str, Any], *, strict: bool
    ) -> dict[str, Any]:
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
                raise ValueError(
                    f"unknown fields in strict schema: {sorted(unknown)}"
                )
        return coerced
