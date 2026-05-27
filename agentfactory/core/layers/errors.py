"""Layer 6 — ErrorLayer.

Adds structured recovery policy on top of PolicyLayer. Every component here
targets a named entry in :mod:`agentfactory.core.catalog.errors` so retry,
fallback, escalation, and compensation logic is expressed against a finite
vocabulary rather than ad-hoc exception types.

Slots:

* ``retry_policies`` — per-error-class :class:`RetryPolicy`.
* ``fallback_agent`` — agent ID to delegate to on terminal failure.
* ``escalation_rules`` — ordered triggers and actions.
* ``circuit_breaker`` — optional shared breaker.
* ``compensation_actions`` — error-key -> granted tool key invoked as rollback.
* ``partial_result_policy`` — discard / return_partial / raise.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

from agentfactory.core.catalog.errors import ERROR_REGISTRY
from agentfactory.core.layers.policy import PolicyLayer


# ---------------------------------------------------------------------------
# Recovery component value objects
# ---------------------------------------------------------------------------


BackoffStrategy = Literal["none", "linear", "exponential"]


class RetryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_attempts: PositiveInt = 3
    backoff: BackoffStrategy = "exponential"
    base_delay_ms: PositiveInt = 250
    max_delay_ms: PositiveInt = 30_000

    @model_validator(mode="after")
    def _delay_ordering(self) -> Self:
        if self.max_delay_ms < self.base_delay_ms:
            raise ValueError("max_delay_ms must be >= base_delay_ms")
        return self


# Triggers that ESCALATION rules can fire on. Either a registered error key
# or one of the framework's meta-triggers.
META_TRIGGERS: frozenset[str] = frozenset(
    {"cycles_exceeded", "budget_80pct", "budget_exhausted", "depth_exceeded"}
)


EscalationAction = Literal["raise", "fallback", "human_review", "log_only"]


class EscalationRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trigger: str = Field(
        ...,
        description="Error class key (from ERROR_REGISTRY) or meta-trigger.",
    )
    action: EscalationAction = "raise"
    notes: str = Field(default="", max_length=256)

    @field_validator("trigger")
    @classmethod
    def _validate_trigger(cls, v: str) -> str:
        if v in META_TRIGGERS:
            return v
        if not ERROR_REGISTRY.has(v):
            raise ValueError(
                f"trigger {v!r} is not in ERROR_REGISTRY and is not a "
                f"meta-trigger ({sorted(META_TRIGGERS)})"
            )
        return v


class CircuitBreaker(BaseModel):
    """Open the circuit after N consecutive failures; recover after T seconds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    failure_threshold: PositiveInt = 5
    recovery_seconds: PositiveFloat = 30.0
    half_open_calls: PositiveInt = 1


class PartialResultPolicy(StrEnum):
    DISCARD = "discard"
    RETURN_PARTIAL = "return_partial"
    RAISE = "raise"


# ---------------------------------------------------------------------------
# The layer
# ---------------------------------------------------------------------------


class ErrorLayer(PolicyLayer):
    """Layer 6 — extends PolicyLayer with structured recovery policy."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    retry_policies: dict[str, RetryPolicy] = Field(default_factory=dict)
    fallback_agent: str | None = None
    escalation_rules: tuple[EscalationRule, ...] = Field(default_factory=tuple)
    circuit_breaker: CircuitBreaker | None = None
    compensation_actions: dict[str, str] = Field(default_factory=dict)
    partial_result_policy: PartialResultPolicy = PartialResultPolicy.RAISE

    # --- field-level validation -------------------------------------------

    @field_validator("retry_policies")
    @classmethod
    def _validate_retry_keys(
        cls, v: dict[str, RetryPolicy]
    ) -> dict[str, RetryPolicy]:
        for key in v:
            if not ERROR_REGISTRY.has(key):
                raise ValueError(
                    f"retry_policies references unknown error class {key!r}"
                )
            if not ERROR_REGISTRY.get(key).retryable:
                raise ValueError(
                    f"error class {key!r} is not retryable; "
                    f"do not configure a RetryPolicy for it"
                )
        return v

    @field_validator("escalation_rules", mode="before")
    @classmethod
    def _coerce_escalations(cls, v: object) -> tuple[EscalationRule, ...]:
        if v is None:
            return ()
        if isinstance(v, (list, tuple)):
            return tuple(v)
        raise TypeError("escalation_rules must be a list or tuple")

    # --- cross-slot consistency -------------------------------------------

    @model_validator(mode="after")
    def _check_error_consistency(self) -> Self:
        # fallback_agent can't be self.
        if self.fallback_agent is not None and self.fallback_agent == self.id:
            raise ValueError(
                f"fallback_agent {self.fallback_agent!r} cannot be this agent"
            )

        # compensation_actions: error keys must exist; tool keys must be granted.
        for err_key, tool_key in self.compensation_actions.items():
            if not ERROR_REGISTRY.has(err_key):
                raise ValueError(
                    f"compensation_actions[{err_key!r}] references unknown "
                    f"error class"
                )
            if tool_key not in self.tool_grants:
                raise ValueError(
                    f"compensation_actions[{err_key!r}] -> {tool_key!r} is "
                    f"not in tool_grants"
                )

        # human_review escalation action requires at least one HITL tool grant.
        for rule in self.escalation_rules:
            if rule.action == "human_review" and not self.hitl_grants():
                raise ValueError(
                    f"escalation rule {rule.trigger!r} requests human_review "
                    f"but no HITL tools are granted"
                )

        # fallback escalation action requires a fallback_agent.
        for rule in self.escalation_rules:
            if rule.action == "fallback" and self.fallback_agent is None:
                raise ValueError(
                    f"escalation rule {rule.trigger!r} requests fallback but "
                    f"fallback_agent is not configured"
                )
        return self

    # --- introspection -----------------------------------------------------

    def action_for(self, error_key: str) -> str:
        """Resolve the effective action for a given error class.

        Precedence: explicit retry_policy (-> "retry"), explicit escalation
        rule, otherwise the descriptor's default_action."""
        if error_key in self.retry_policies:
            return "retry"
        for rule in self.escalation_rules:
            if rule.trigger == error_key:
                return rule.action
        return ERROR_REGISTRY.get(error_key).default_action
