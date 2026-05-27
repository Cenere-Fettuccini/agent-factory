"""Layer 7 — LogLayer.

Adds pluggable observability on top of ErrorLayer. Sinks are referenced by
key from :mod:`agentfactory.core.catalog.sinks`; per-sink configuration
(file paths, credentials, hostnames) lives on the layer itself so the catalog
stays config-free and a Langfuse setup is a one-line swap.

Slots:

* ``primary_sink`` — required sink key (events always go here).
* ``secondary_sinks`` — additional fan-out targets.
* ``sink_configs`` — per-sink config dicts validated against the sink's
  declared :class:`IOSchema`.
* ``sampling`` — overall and per-event-kind sampling rates.
* ``redaction`` — field paths to scrub before emit.
* ``trace_context_enabled`` — propagate distributed trace IDs.

The final concrete agent is just ``LogLayer`` — by composing this layer you
have walked all seven steps of the contract chain and the resulting class is
fully specified and instantiable.
"""

from __future__ import annotations

from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from agentfactory.core.catalog.sinks import SINK_REGISTRY
from agentfactory.core.layers.errors import ErrorLayer


# ---------------------------------------------------------------------------
# Logging primitives
# ---------------------------------------------------------------------------


class SamplingRule(BaseModel):
    """Probabilistic sampling. ``rate`` applies globally; ``per_kind`` overrides."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rate: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    per_kind: dict[str, Annotated[float, Field(ge=0.0, le=1.0)]] = Field(
        default_factory=dict,
        description="Event-kind specific sampling rates that override `rate`.",
    )


class RedactionRule(BaseModel):
    """Field paths to scrub before events leave the process."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fields: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    replacement: str = "[REDACTED]"

    @field_validator("fields", mode="before")
    @classmethod
    def _coerce(cls, v: object) -> tuple[str, ...]:
        if v is None:
            return ()
        if isinstance(v, (list, tuple)):
            return tuple(str(x) for x in v)
        raise TypeError("fields must be a list or tuple of strings")


# ---------------------------------------------------------------------------
# The layer
# ---------------------------------------------------------------------------


class LogLayer(ErrorLayer):
    """Layer 7 — extends ErrorLayer with pluggable observability."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    primary_sink: str = Field(
        default="null",
        description="SINK_REGISTRY key. Defaults to the no-op sink.",
    )
    secondary_sinks: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=8,
        description="Additional fan-out sinks beyond the primary.",
    )
    sink_configs: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-sink config keyed by sink key.",
    )
    sampling: SamplingRule = Field(default_factory=SamplingRule)
    redaction: RedactionRule = Field(default_factory=RedactionRule)
    trace_context_enabled: bool = False

    # --- coercion ----------------------------------------------------------

    @field_validator("secondary_sinks", mode="before")
    @classmethod
    def _coerce_secondary(cls, v: object) -> tuple[str, ...]:
        if v is None:
            return ()
        if isinstance(v, (list, tuple, set, frozenset)):
            return tuple(str(x) for x in v)
        raise TypeError("secondary_sinks must be an iterable of sink keys")

    # --- field validation --------------------------------------------------

    @field_validator("primary_sink")
    @classmethod
    def _validate_primary(cls, v: str) -> str:
        if not SINK_REGISTRY.has(v):
            raise ValueError(
                f"primary_sink {v!r} is not in SINK_REGISTRY "
                f"(core: {SINK_REGISTRY.core_keys()}, "
                f"ext: {SINK_REGISTRY.extension_keys()})"
            )
        return v

    @field_validator("secondary_sinks")
    @classmethod
    def _validate_secondary(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        for key in v:
            if key in seen:
                raise ValueError(f"duplicate sink in secondary_sinks: {key!r}")
            seen.add(key)
            if not SINK_REGISTRY.has(key):
                raise ValueError(
                    f"secondary sink {key!r} is not in SINK_REGISTRY"
                )
        return v

    # --- cross-slot consistency -------------------------------------------

    @model_validator(mode="after")
    def _check_log_consistency(self) -> Self:
        # Primary cannot also appear in secondaries — that's just duplicate emit.
        if self.primary_sink in self.secondary_sinks:
            raise ValueError(
                f"primary_sink {self.primary_sink!r} must not appear in "
                f"secondary_sinks"
            )

        all_sinks: tuple[str, ...] = (self.primary_sink,) + self.secondary_sinks

        # Validate sink_configs entries against their sink's declared schema.
        for sink_key, cfg in self.sink_configs.items():
            if sink_key not in all_sinks:
                raise ValueError(
                    f"sink_configs[{sink_key!r}] references a sink not in "
                    f"primary_sink/secondary_sinks"
                )
            desc = SINK_REGISTRY.get(sink_key)
            if desc.config_schema is None:
                if cfg:
                    raise ValueError(
                        f"sink {sink_key!r} accepts no config but supplied: "
                        f"{sorted(cfg)}"
                    )
                continue
            # Validate the user config against the sink's declared schema.
            desc.config_schema.validate_payload(cfg, strict=True)

        # Every sink that has required config fields must have an entry.
        for sink_key in all_sinks:
            desc = SINK_REGISTRY.get(sink_key)
            if desc.config_schema is None:
                continue
            required = {
                fname
                for fname, spec in desc.config_schema.fields.items()
                if spec.required
            }
            if not required:
                continue
            cfg = self.sink_configs.get(sink_key, {})
            missing = required - set(cfg)
            if missing:
                raise ValueError(
                    f"sink {sink_key!r} is missing required config fields: "
                    f"{sorted(missing)}"
                )
        return self

    # --- introspection -----------------------------------------------------

    def active_sinks(self) -> tuple[str, ...]:
        """All sinks events will fan out to: primary first, then secondaries."""
        return (self.primary_sink,) + self.secondary_sinks
