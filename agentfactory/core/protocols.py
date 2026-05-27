"""Component protocols — the shape every catalog entry must conform to.

Each layer (Model, IO, Tool, Policy, Error, Log) accepts a *bag* of components
in parallel. To be a valid component, an object must implement the matching
``Protocol`` here. Protocols are ``runtime_checkable`` so the registry can
validate registrations at the boundary; static checkers also use them to keep
slots correctly typed.

These protocols intentionally describe only the *minimum* surface every
component shares. Layer-specific behavior lives on subclasses defined in
``agentfactory.core.catalog`` and ``agentfactory.core.layers``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Component(Protocol):
    """Root protocol for any catalog component.

    Every component carries a stable string ``key`` (its catalog name) and a
    ``kind`` discriminator so the registry can shard storage by component type
    and reject cross-kind registrations.
    """

    key: str
    kind: str


@runtime_checkable
class ModelComponent(Component, Protocol):
    """A model-layer component: model selection, fallback chain, gen params, etc."""

    kind: str  # must equal "model"


@runtime_checkable
class IOComponent(Component, Protocol):
    """An IO-layer component drawn from the standardized IO lexicon."""

    kind: str  # must equal "io"


@runtime_checkable
class ToolComponent(Component, Protocol):
    """A tool-layer component. HITL tools are ordinary ToolComponents."""

    kind: str  # must equal "tool"


@runtime_checkable
class PolicyComponent(Component, Protocol):
    """A policy-layer component: ACLs, cycle limits, recursion limits, budgets."""

    kind: str  # must equal "policy"


@runtime_checkable
class ErrorComponent(Component, Protocol):
    """An error-layer component: retry policies, fallbacks, escalation rules."""

    kind: str  # must equal "error"


@runtime_checkable
class LogComponent(Component, Protocol):
    """A log-layer component: sinks, samplers, redactors, trace propagators."""

    kind: str  # must equal "log"


# Frozen set of valid `kind` discriminators. Registries cross-check against
# this to catch typos before they propagate.
COMPONENT_KINDS: frozenset[str] = frozenset(
    {"model", "io", "tool", "policy", "error", "log"}
)
