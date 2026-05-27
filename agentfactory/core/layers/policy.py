"""Layer 5 — PolicyLayer.

Adds enforcement primitives on top of ToolLayer. This is the layer security,
budgeting, and orchestration consumers read. None of these limits are
suggestions: the executor checks them at runtime, but PolicyLayer also
rejects configurations that are internally inconsistent (e.g.
``max_recursion_depth=0`` with non-empty ``subagent_grants``).

Slots:

* ``caller_allowlist`` — who may invoke this agent (``None`` = unrestricted).
* ``tool_acl`` — per-caller tool restrictions (subset of ``tool_grants``).
* ``max_cycles`` — max iterations of the agent's reasoning loop.
* ``max_recursion_depth`` — max depth of subagent spawning rooted at this agent.
* ``cost_budget_usd`` — hard USD cap per invocation.
* ``rate_limit`` — optional rate ceiling.
* ``time_budget`` — wall-clock ceiling per invocation.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

from agentfactory.core.layers.tools import ToolLayer


# ---------------------------------------------------------------------------
# Policy primitives (value objects)
# ---------------------------------------------------------------------------


class RateLimit(BaseModel):
    """Calls-per-window ceiling. Window is wall-clock seconds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_calls: PositiveInt
    window_seconds: PositiveInt
    burst: PositiveInt | None = Field(
        default=None,
        description="Optional short-window burst allowance.",
    )

    @model_validator(mode="after")
    def _burst_ge_max(self) -> Self:
        if self.burst is not None and self.burst < self.max_calls:
            raise ValueError("burst must be >= max_calls when set")
        return self


class TimeBudget(BaseModel):
    """Wall-clock ceilings, split per-call and total."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    per_call_seconds: PositiveFloat = 30.0
    total_seconds: PositiveFloat = 300.0

    @model_validator(mode="after")
    def _total_ge_per_call(self) -> Self:
        if self.total_seconds < self.per_call_seconds:
            raise ValueError(
                "total_seconds must be >= per_call_seconds"
            )
        return self


# ---------------------------------------------------------------------------
# The layer
# ---------------------------------------------------------------------------


class PolicyLayer(ToolLayer):
    """Layer 5 — extends ToolLayer with enforcement primitives."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    caller_allowlist: frozenset[str] | None = Field(
        default=None,
        description="Caller IDs permitted to invoke this agent. None = unrestricted.",
    )
    tool_acl: dict[str, frozenset[str]] = Field(
        default_factory=dict,
        description="Per-caller tool restrictions. Caller key -> allowed subset of tool_grants.",
    )
    max_cycles: PositiveInt = Field(
        default=10,
        description="Max iterations of the agent's reasoning loop per invocation.",
    )
    max_recursion_depth: NonNegativeInt = Field(
        default=0,
        description="Max depth of subagent spawning rooted at this agent.",
    )
    cost_budget_usd: PositiveFloat = Field(
        default=1.0,
        description="Hard USD cap per invocation.",
    )
    rate_limit: RateLimit | None = None
    time_budget: TimeBudget = Field(default_factory=TimeBudget)

    # --- coercion ----------------------------------------------------------

    @field_validator("caller_allowlist", mode="before")
    @classmethod
    def _coerce_allowlist(cls, v: object) -> frozenset[str] | None:
        if v is None:
            return None
        if isinstance(v, (list, tuple, set, frozenset)):
            return frozenset(str(x) for x in v)
        raise TypeError("caller_allowlist must be an iterable of strings or None")

    @field_validator("tool_acl", mode="before")
    @classmethod
    def _coerce_acl(
        cls, v: object
    ) -> dict[str, frozenset[str]]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise TypeError("tool_acl must be a dict")
        out: dict[str, frozenset[str]] = {}
        for caller, allowed in v.items():
            if not isinstance(allowed, (list, tuple, set, frozenset)):
                raise TypeError(
                    f"tool_acl[{caller!r}] must be an iterable of tool keys"
                )
            out[str(caller)] = frozenset(str(x) for x in allowed)
        return out

    # --- cross-slot consistency -------------------------------------------

    @model_validator(mode="after")
    def _check_policy_consistency(self) -> Self:
        # An agent declaring recursion depth 0 must not grant subagents.
        if self.max_recursion_depth == 0 and self.subagent_grants:
            raise ValueError(
                f"max_recursion_depth=0 forbids subagent_grants "
                f"(declared: {sorted(self.subagent_grants)})"
            )

        # ACL entries must reference real tool grants. Anything else is a
        # silent failure waiting to happen.
        for caller, allowed in self.tool_acl.items():
            unknown = allowed - self.tool_grants
            if unknown:
                raise ValueError(
                    f"tool_acl[{caller!r}] references tools not in "
                    f"tool_grants: {sorted(unknown)}"
                )

        # If a caller_allowlist is set, every ACL caller must be in it —
        # otherwise the ACL has dead entries.
        if self.caller_allowlist is not None:
            dead = set(self.tool_acl) - self.caller_allowlist
            if dead:
                raise ValueError(
                    f"tool_acl has entries for callers not in caller_allowlist: "
                    f"{sorted(dead)}"
                )
        return self

    # --- introspection -----------------------------------------------------

    def allowed_tools_for(self, caller: str) -> frozenset[str]:
        """Tools this agent will let ``caller`` invoke.

        Resolution: if the caller is denied by ``caller_allowlist`` return
        empty; if no ACL entry exists for the caller, fall back to all
        ``tool_grants``; otherwise return the ACL intersection.
        """
        if self.caller_allowlist is not None and caller not in self.caller_allowlist:
            return frozenset()
        return self.tool_acl.get(caller, self.tool_grants)
