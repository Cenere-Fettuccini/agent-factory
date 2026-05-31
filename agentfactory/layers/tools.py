"""Layer 3: tool grants and the caller allowlist."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentfactory.catalog.tools import TOOLS


class ToolsLayer(BaseModel):
    """Which catalogued tools this agent may call, and who may call it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_grants: list[str] = []
    caller_allowlist: list[str] = []
    # Optional per-tool cap on how many times this agent may invoke a given tool
    # in one run, keyed by tool id (a subagent call is a tool call, so this also
    # bounds an A->B edge). An absent entry means "no per-tool cap" — only the
    # global policy.max_tool_calls applies.
    tool_call_caps: dict[str, int] = Field(default_factory=dict)

    @field_validator("tool_grants")
    @classmethod
    def _grants_in_catalog(cls, value: list[str]) -> list[str]:
        unknown = [g for g in value if not TOOLS.contains(g)]
        if unknown:
            raise ValueError(
                f"tool_grants {unknown} are not in the tool catalog; "
                f"known: {TOOLS.ids()}"
            )
        return value

    @field_validator("tool_call_caps")
    @classmethod
    def _caps_positive(cls, value: dict[str, int]) -> dict[str, int]:
        bad = {k: v for k, v in value.items() if v < 1}
        if bad:
            raise ValueError(f"tool_call_caps values must be >= 1: {bad}")
        return value
