"""Layer 4 — ToolLayer.

Adds the tool/subagent surface to IOLayer. HITL is not a special concept here
— it lives in the same ``tool_grants`` set, distinguished by the descriptor's
``requires_human`` flag. A helper exposes the HITL subset for consumers that
care (executors, policy enforcement, audit).

Slots:

* ``tool_grants`` — frozenset of tool keys, validated against TOOL_REGISTRY.
* ``subagent_grants`` — frozenset of agent IDs callable as tools.
* ``aliases`` — local rename map (alias → registry key).
* ``defaults`` — per-tool argument presets validated against the tool's
  parameter schema.
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from agentfactory.core.catalog.tools import TOOL_REGISTRY
from agentfactory.core.layers.io import IOLayer


class ToolLayer(IOLayer):
    """Layer 4 — extends IOLayer with tool, subagent, alias, and default slots."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    tool_grants: frozenset[str] = Field(
        default_factory=frozenset,
        description="Tool keys this agent may invoke. Includes HITL tools.",
    )
    subagent_grants: frozenset[str] = Field(
        default_factory=frozenset,
        description="Agent IDs this agent may call as tools.",
    )
    aliases: dict[str, str] = Field(
        default_factory=dict,
        description="Local alias → registered tool key.",
    )
    defaults: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Default argument values keyed by tool key.",
    )

    # --- coercion ----------------------------------------------------------

    @field_validator("tool_grants", "subagent_grants", mode="before")
    @classmethod
    def _coerce_set(cls, v: object) -> frozenset[str]:
        if v is None:
            return frozenset()
        if isinstance(v, (list, tuple, set, frozenset)):
            return frozenset(str(x) for x in v)
        raise TypeError("must be an iterable of strings")

    # --- field validation --------------------------------------------------

    @field_validator("tool_grants")
    @classmethod
    def _validate_tool_grants(cls, v: frozenset[str]) -> frozenset[str]:
        for key in v:
            if not TOOL_REGISTRY.has(key):
                raise ValueError(
                    f"tool {key!r} is not in TOOL_REGISTRY "
                    f"(core: {TOOL_REGISTRY.core_keys()}, "
                    f"ext: {TOOL_REGISTRY.extension_keys()})"
                )
        return v

    @field_validator("aliases")
    @classmethod
    def _validate_aliases(cls, v: dict[str, str]) -> dict[str, str]:
        for alias, target in v.items():
            if not alias or not alias.isidentifier():
                raise ValueError(
                    f"alias {alias!r} must be a valid Python identifier"
                )
            if not TOOL_REGISTRY.has(target):
                raise ValueError(
                    f"alias {alias!r} targets unknown tool {target!r}"
                )
        return v

    # --- cross-slot consistency -------------------------------------------

    @model_validator(mode="after")
    def _check_tool_consistency(self) -> Self:
        # Aliases must not collide with real tool keys or with each other's targets
        # in a way that creates ambiguity.
        for alias in self.aliases:
            if TOOL_REGISTRY.has(alias):
                raise ValueError(
                    f"alias {alias!r} collides with an existing tool key"
                )

        # defaults: every key must be a granted tool, every default arg must
        # exist in the tool's parameter schema (when one is declared).
        for tool_key, args in self.defaults.items():
            if tool_key not in self.tool_grants:
                raise ValueError(
                    f"defaults reference tool {tool_key!r} which is not in "
                    f"tool_grants"
                )
            desc = TOOL_REGISTRY.get(tool_key)
            if desc.parameters is None:
                if args:
                    raise ValueError(
                        f"tool {tool_key!r} takes no parameters but defaults "
                        f"supplied {sorted(args)}"
                    )
                continue
            unknown = set(args) - set(desc.parameters.fields)
            if unknown:
                raise ValueError(
                    f"defaults for tool {tool_key!r} reference unknown "
                    f"parameters: {sorted(unknown)}"
                )
        return self

    # --- introspection helpers --------------------------------------------

    def hitl_grants(self) -> frozenset[str]:
        """The subset of ``tool_grants`` that route to a human."""
        return frozenset(
            k for k in self.tool_grants if TOOL_REGISTRY.get(k).requires_human
        )

    def non_hitl_grants(self) -> frozenset[str]:
        """The subset of ``tool_grants`` that do not require a human."""
        return self.tool_grants - self.hitl_grants()

    def declared_side_effects(self) -> frozenset[str]:
        """Union of side-effect categories across all granted tools.

        Used by PolicyLayer (next layer up) to detect e.g. a network-using
        agent that has not declared network permission."""
        out: set[str] = set()
        for k in self.tool_grants:
            out.update(TOOL_REGISTRY.get(k).side_effects)
        return frozenset(out)
