"""The graph payload: nodes (agents) and edges ("A calls B").

Every request carries its own graph. The server holds no session state.
A node carries a one-line description plus *partial* layer config — any field
left unset is fair game for the Resolver to fill.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraphNode(BaseModel):
    """One agent in the graph. Layer fields are partial dicts, filled lazily."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    name: str | None = None
    version: str = "0.1.0"
    tags: list[str] = Field(default_factory=list)

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
    """A project: a set of agent nodes wired by call edges."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def node_ids(self) -> list[str]:
        return [n.id for n in self.nodes]

    def get(self, node_id: str) -> GraphNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)
