"""The graph payload: nodes (agents) and edges ("A calls B").

Every request carries its own graph. The server holds no session state.
A node carries a one-line description plus *partial* layer config — any field
left unset is fair game for the Resolver to fill.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# A top-tier node may be an entry point. ``user_query`` agents start from a user
# request; ``auto_action`` agents are triggered automatically. Both resolve their
# query down through the tiers.
TriggerKind = Literal["user_query", "auto_action"]


class ToolDefField(BaseModel):
    """One argument or return field of an authored tool.

    Field types reuse the framework's IO type lexicon (``text``/``json``/… —
    see ``agentfactory.catalog.io_types``) so no new type vocabulary is needed.
    """

    model_config = ConfigDict(extra="forbid")

    type_key: str
    required: bool = True
    description: str = ""


class ToolDef(BaseModel):
    """A tool authored in the UI, carried with the graph (stateless).

    The framework's tool catalog is code-registered and needs a real callable, so
    an authored tool is materialised transiently with a stub callable for
    validation/preview/dry-run, and exported as a typed stub the user fills in.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    args: dict[str, ToolDefField] = Field(default_factory=dict)
    returns: dict[str, ToolDefField] | None = None


class GraphNode(BaseModel):
    """One agent in the graph. Layer fields are partial dicts, filled lazily."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    name: str | None = None
    version: str = "0.1.0"
    tags: list[str] = Field(default_factory=list)

    # Network role: which tier this agent sits in (a name from ``Graph.layers``).
    # None means unassigned. ``trigger`` marks a top-tier entry point.
    layer: str | None = None
    trigger: TriggerKind | None = None

    # Partial layer configs. None means "unset" — the Resolver may fill it.
    model: dict[str, Any] | None = None
    io: dict[str, Any] | None = None
    tools: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    errors: dict[str, Any] | None = None
    telemetry: dict[str, Any] | None = None


class GraphEdge(BaseModel):
    """A directed call edge: ``source`` calls ``target`` as a subagent."""

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str


class Graph(BaseModel):
    """A project: a set of agent nodes wired by call edges.

    ``layers`` names the network tiers top-to-bottom (e.g. refinement →
    orchestrator → tools); a call edge may only cross from one tier to the one
    directly below it. ``tool_defs`` carries any tools authored in the UI.
    """

    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)
    tool_defs: list[ToolDef] = Field(default_factory=list)

    def node_ids(self) -> list[str]:
        return [n.id for n in self.nodes]

    def get(self, node_id: str) -> GraphNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def layer_index(self, name: str | None) -> int | None:
        """Position of a tier in the top-to-bottom order, or None if unknown."""
        if name is None or name not in self.layers:
            return None
        return self.layers.index(name)
