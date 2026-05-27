"""Core error catalog.

A standardized hierarchy of error *classes* (not exception instances). Each
descriptor names a recoverable or fatal failure mode that the executor maps
real exceptions onto, and that policies in ErrorLayer target by key. Keeping
the catalog finite means retry/fallback/escalation rules are expressible as
small dicts rather than ad-hoc if/elif chains over exception types.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentfactory.core.registry import Registry

DefaultAction = Literal["retry", "fallback", "escalate", "raise"]


class ErrorClassDescriptor(BaseModel):
    """One catalog entry describing an abstract failure mode."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["error"] = "error"
    key: str = Field(..., min_length=1, max_length=64)
    description: str = Field(default="", max_length=512)

    retryable: bool = Field(
        default=False,
        description="Whether a retry has any chance of changing the outcome.",
    )
    default_action: DefaultAction = Field(
        default="raise",
        description="Action when no explicit policy is supplied.",
    )
    is_fatal: bool = Field(
        default=False,
        description="True if no recovery action other than fail-fast is sensible.",
    )


ERROR_REGISTRY: Final[Registry[ErrorClassDescriptor]] = Registry(
    kind="error", component_type=ErrorClassDescriptor
)


def _bootstrap_core() -> None:
    core: tuple[ErrorClassDescriptor, ...] = (
        ErrorClassDescriptor(
            key="rate_limit",
            description="Upstream provider returned a rate-limit response.",
            retryable=True,
            default_action="retry",
        ),
        ErrorClassDescriptor(
            key="timeout",
            description="A call exceeded its time budget.",
            retryable=True,
            default_action="retry",
        ),
        ErrorClassDescriptor(
            key="model_failure",
            description="Model API returned an error (5xx, malformed response).",
            retryable=True,
            default_action="fallback",
        ),
        ErrorClassDescriptor(
            key="tool_failure",
            description="A tool invocation raised or returned ok=False.",
            retryable=False,
            default_action="escalate",
        ),
        ErrorClassDescriptor(
            key="validation_error",
            description="Input or output failed schema validation.",
            retryable=False,
            default_action="raise",
        ),
        ErrorClassDescriptor(
            key="policy_violation",
            description="Caller / ACL / depth / cycles check failed.",
            retryable=False,
            default_action="raise",
            is_fatal=True,
        ),
        ErrorClassDescriptor(
            key="budget_exceeded",
            description="Cost or token budget was breached.",
            retryable=False,
            default_action="escalate",
        ),
        ErrorClassDescriptor(
            key="hitl_denied",
            description="A human declined or did not respond to an HITL call.",
            retryable=False,
            default_action="raise",
        ),
    )
    for entry in core:
        ERROR_REGISTRY._register_core(entry)
    ERROR_REGISTRY.seal_core()


_bootstrap_core()
