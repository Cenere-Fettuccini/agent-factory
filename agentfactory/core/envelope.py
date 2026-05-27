"""Typed messaging envelope.

Every cross-agent or executor interaction is wrapped in one of:

* :class:`AgentRequest`  — input payload + caller identity + trace context.
* :class:`AgentResponse` — output payload + usage + audit trail.
* :class:`AgentError`    — structured failure with an :mod:`agentfactory.core.catalog.errors` class key.
* :class:`AgentEvent`    — observability records emitted during a run.

The payload fields are deliberately ``dict[str, Any]``: the actual shape is
enforced by the agent's :class:`IOSchema` at the executor boundary, so the
envelope stays one stable type across every agent in the system. If you want
tighter compile-time shapes, subclass and narrow ``payload``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Trace context
# ---------------------------------------------------------------------------


class TraceContext(BaseModel):
    """Distributed tracing carrier. Propagates across subagent calls."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trace_id: str = Field(default_factory=_new_id)
    span_id: str = Field(default_factory=_new_id)
    parent_span_id: str | None = None

    def child(self) -> "TraceContext":
        """Derive a child span sharing the trace id."""
        return TraceContext(
            trace_id=self.trace_id,
            span_id=_new_id(),
            parent_span_id=self.span_id,
        )


# ---------------------------------------------------------------------------
# Request / response
# ---------------------------------------------------------------------------


class AgentRequest(BaseModel):
    """Input envelope. Carries the payload plus caller identity and trace context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = Field(default_factory=_new_id)
    issued_at: datetime = Field(default_factory=_now)

    target_agent_id: str
    caller_id: str = Field(
        default="anonymous",
        description="Identity used for caller_allowlist / tool_acl checks.",
    )
    payload: dict[str, Any] = Field(default_factory=dict)

    trace: TraceContext = Field(default_factory=TraceContext)
    deadline: datetime | None = Field(
        default=None,
        description="Hard cutoff; executor must abort by this UTC time.",
    )


class Usage(BaseModel):
    """Per-run resource accounting. Fields aggregate across all model/tool calls."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    cache_read_tokens: NonNegativeInt = 0
    cache_write_tokens: NonNegativeInt = 0
    cost_usd: float = Field(default=0.0, ge=0.0)
    duration_ms: NonNegativeInt = 0
    model_calls: NonNegativeInt = 0
    tool_calls: NonNegativeInt = 0
    cycles: NonNegativeInt = 0


class AgentResponse(BaseModel):
    """Output envelope. Carries the payload, usage stats, and a trace pointer back."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    completed_at: datetime = Field(default_factory=_now)

    agent_id: str
    payload: dict[str, Any] = Field(default_factory=dict)

    usage: Usage = Field(default_factory=Usage)
    trace: TraceContext

    partial: bool = Field(
        default=False,
        description="True when the response is a partial result under a "
        "PartialResultPolicy.RETURN_PARTIAL configuration.",
    )


# ---------------------------------------------------------------------------
# Structured error
# ---------------------------------------------------------------------------


class AgentError(BaseModel):
    """Structured failure result. Maps onto an entry in ERROR_REGISTRY."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    raised_at: datetime = Field(default_factory=_now)

    agent_id: str
    error_class: str = Field(
        ...,
        description="Key in ERROR_REGISTRY (rate_limit, timeout, ...).",
    )
    message: str
    retryable: bool = False
    partial_payload: dict[str, Any] | None = None

    trace: TraceContext


# ---------------------------------------------------------------------------
# Observability events (discriminated union)
# ---------------------------------------------------------------------------


class _EventBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(default_factory=_new_id)
    emitted_at: datetime = Field(default_factory=_now)
    agent_id: str
    trace: TraceContext
    kind: str  # discriminator, overridden in subclasses


class CycleEvent(_EventBase):
    """Emitted at the start of each reasoning cycle."""

    kind: Literal["cycle"] = "cycle"
    cycle_index: NonNegativeInt


class ModelCallEvent(_EventBase):
    """A call to a model. Usage is for this call only — aggregates live on Usage."""

    kind: Literal["model_call"] = "model_call"
    model_key: str
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    duration_ms: NonNegativeInt
    cost_usd: float = Field(ge=0.0)


class ToolCallEvent(_EventBase):
    """A tool invocation. Includes the resolved key and the args sent."""

    kind: Literal["tool_call"] = "tool_call"
    tool_key: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResultEvent(_EventBase):
    """A tool's response."""

    kind: Literal["tool_result"] = "tool_result"
    tool_key: str
    ok: bool
    duration_ms: NonNegativeInt
    error: str | None = None


class HITLEvent(_EventBase):
    """Emitted when a human-in-the-loop tool is invoked or resolved."""

    kind: Literal["hitl"] = "hitl"
    tool_key: str
    phase: Literal["requested", "responded", "denied", "timeout"]
    note: str = ""


class BudgetEvent(_EventBase):
    """Budget checkpoint: emitted at thresholds (e.g. 80%, exhausted)."""

    kind: Literal["budget"] = "budget"
    metric: Literal["cost", "tokens", "time", "cycles"]
    used: float
    limit: float
    threshold: Literal["50pct", "80pct", "exhausted"]


class SpawnEvent(_EventBase):
    """Subagent spawn. Carries the child request id and depth."""

    kind: Literal["spawn"] = "spawn"
    child_agent_id: str
    child_request_id: str
    depth: NonNegativeInt


class ErrorEvent(_EventBase):
    """An error was raised or handled mid-run."""

    kind: Literal["error"] = "error"
    error_class: str
    message: str
    handled: bool


AgentEvent = Annotated[
    Union[
        CycleEvent,
        ModelCallEvent,
        ToolCallEvent,
        ToolResultEvent,
        HITLEvent,
        BudgetEvent,
        SpawnEvent,
        ErrorEvent,
    ],
    Field(discriminator="kind"),
]
"""Discriminated union of all observability events. Sinks accept ``AgentEvent``."""
