"""Layer 3: tool grants and the caller allowlist."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from agentfactory.catalog.tools import TOOLS


class ToolsLayer(BaseModel):
    """Which catalogued tools this agent may call, and who may call it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_grants: list[str] = []
    caller_allowlist: list[str] = []

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
