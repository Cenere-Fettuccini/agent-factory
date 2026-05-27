"""Layer 2 — ModelLayer.

Adds the *which-brain* dimension to BaseAgent. Holds the parallel slots:

* ``primary`` — the default model key (resolved against ``MODEL_REGISTRY``).
* ``fallback_chain`` — ordered keys to try if the primary fails or is over budget.
* ``routing_policy`` — strategy for picking a model dynamically (subset of a
  sealed family of policies; ``StaticRouting`` means always use ``primary``).
* ``generation_params`` — temperature, top_p, max output tokens.
* ``cache_strategy`` — prompt-cache configuration.

Every model key in any slot is validated against ``MODEL_REGISTRY`` at
construction time, so a typo or an unregistered extension fails fast rather
than at the first runtime API call.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

from agentfactory.core.base import BaseAgent
from agentfactory.core.catalog.models import MODEL_REGISTRY


# ---------------------------------------------------------------------------
# Parallel-slot value objects
# ---------------------------------------------------------------------------


class GenerationParams(BaseModel):
    """Sampling and length controls applied to every model call this agent makes.

    Layered enforcement: Pydantic verifies the value ranges; the executor
    re-checks ``max_output_tokens`` against the chosen model's context window
    at call time (since extensions can register models with different limits).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    temperature: Annotated[float, Field(ge=0.0, le=2.0)] = 1.0
    top_p: Annotated[float, Field(gt=0.0, le=1.0)] = 1.0
    max_output_tokens: PositiveInt = 4096
    stop_sequences: tuple[str, ...] = Field(default_factory=tuple, max_length=8)

    @field_validator("stop_sequences", mode="before")
    @classmethod
    def _coerce_stops(cls, v: object) -> tuple[str, ...]:
        if v is None:
            return ()
        if isinstance(v, (list, tuple)):
            return tuple(str(x) for x in v)
        raise TypeError("stop_sequences must be a list or tuple of strings")


class CacheStrategy(StrEnum):
    """Prompt-cache configuration. Sealed; extensions live elsewhere if needed."""

    NONE = "none"
    EPHEMERAL_5MIN = "ephemeral_5min"
    PERSISTENT_1H = "persistent_1h"


# ---------------------------------------------------------------------------
# Routing policy family (sealed discriminated union)
# ---------------------------------------------------------------------------


class _RoutingBase(BaseModel):
    """Common base for all routing policies. Not user-instantiable."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: str


class StaticRouting(_RoutingBase):
    """Always use the layer's ``primary`` model. The default."""

    kind: Literal["static"] = "static"


class SizeBasedRouting(_RoutingBase):
    """Pick a model based on input token count.

    ``thresholds`` maps an inclusive lower bound (in input tokens) to a model
    key. Selection picks the entry with the largest threshold not exceeding
    the input size. Below the smallest threshold, fall back to ``primary``.
    """

    kind: Literal["by_size"] = "by_size"
    thresholds: dict[Annotated[int, Field(ge=0)], str] = Field(..., min_length=1)

    @field_validator("thresholds")
    @classmethod
    def _validate_thresholds(cls, v: dict[int, str]) -> dict[int, str]:
        for key in v.values():
            if not MODEL_REGISTRY.has(key):
                raise ValueError(
                    f"routing target {key!r} is not in MODEL_REGISTRY"
                )
        return v


class CostBudgetRouting(_RoutingBase):
    """Try cheapest tier first; escalate on policy-violation failure."""

    kind: Literal["by_cost"] = "by_cost"
    escalation_order: tuple[str, ...] = Field(..., min_length=1)

    @field_validator("escalation_order")
    @classmethod
    def _validate_escalation(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for key in v:
            if not MODEL_REGISTRY.has(key):
                raise ValueError(
                    f"escalation target {key!r} is not in MODEL_REGISTRY"
                )
        return v


class LatencyRouting(_RoutingBase):
    """Race a fast model and a primary model; return whichever responds first.

    The race is bounded by ``fast_timeout_ms`` — if the fast model is still
    running at that point, its in-flight response is cancelled and the primary
    response is awaited.
    """

    kind: Literal["by_latency"] = "by_latency"
    fast_model: str
    fast_timeout_ms: PositiveInt = 1500

    @field_validator("fast_model")
    @classmethod
    def _validate_fast(cls, v: str) -> str:
        if not MODEL_REGISTRY.has(v):
            raise ValueError(f"fast_model {v!r} is not in MODEL_REGISTRY")
        return v


RoutingPolicy = Annotated[
    Union[StaticRouting, SizeBasedRouting, CostBudgetRouting, LatencyRouting],
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# The layer itself
# ---------------------------------------------------------------------------


class ModelLayer(BaseAgent):
    """Layer 2 — extends BaseAgent with model selection slots.

    All five slots are independent: an agent can specify only ``primary`` and
    accept defaults for the rest, or supply any parallel combination. Cross-
    slot consistency (referenced keys exist, fallback chain doesn't contain
    duplicates, etc.) is enforced at construction time.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    primary: str = Field(
        ...,
        description="Model registry key for the default model used by this agent.",
    )
    fallback_chain: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=8,
        description="Ordered model keys to try when the primary fails.",
    )
    routing_policy: RoutingPolicy = Field(  # type: ignore[assignment]
        default_factory=StaticRouting,
        description="Strategy for picking a model dynamically.",
    )
    generation_params: GenerationParams = Field(
        default_factory=GenerationParams,
        description="Sampling and length controls applied to every call.",
    )
    cache_strategy: CacheStrategy = Field(
        default=CacheStrategy.NONE,
        description="Prompt-cache configuration.",
    )

    # --- field-level validation --------------------------------------------

    @field_validator("primary")
    @classmethod
    def _validate_primary(cls, v: str) -> str:
        if not MODEL_REGISTRY.has(v):
            raise ValueError(
                f"primary model {v!r} is not in MODEL_REGISTRY "
                f"(core: {MODEL_REGISTRY.core_keys()}, "
                f"ext: {MODEL_REGISTRY.extension_keys()})"
            )
        return v

    @field_validator("fallback_chain", mode="before")
    @classmethod
    def _coerce_fallback(cls, v: object) -> tuple[str, ...]:
        if v is None:
            return ()
        if isinstance(v, (list, tuple)):
            return tuple(str(x) for x in v)
        raise TypeError("fallback_chain must be a list or tuple of model keys")

    @field_validator("fallback_chain")
    @classmethod
    def _validate_fallback(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        for key in v:
            if key in seen:
                raise ValueError(f"duplicate model key in fallback_chain: {key!r}")
            seen.add(key)
            if not MODEL_REGISTRY.has(key):
                raise ValueError(
                    f"fallback model {key!r} is not in MODEL_REGISTRY"
                )
        return v

    # --- cross-slot consistency --------------------------------------------

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        # Primary should not appear in its own fallback chain — that's a
        # config bug, not a graceful degradation.
        if self.primary in self.fallback_chain:
            raise ValueError(
                f"primary model {self.primary!r} must not appear in "
                f"fallback_chain"
            )

        # Generation params must respect the primary model's context window.
        primary_desc = MODEL_REGISTRY.get(self.primary)
        if self.generation_params.max_output_tokens > primary_desc.max_context_tokens:
            raise ValueError(
                f"generation_params.max_output_tokens="
                f"{self.generation_params.max_output_tokens} exceeds primary "
                f"model context window ({primary_desc.max_context_tokens})"
            )
        return self

    # --- convenience -------------------------------------------------------

    def candidate_models(self) -> tuple[str, ...]:
        """The full ordered list of models this layer may use: primary then
        fallback chain. Useful for budgeting and pre-flight validation."""
        return (self.primary,) + self.fallback_chain
